terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
    random = {
      source = "hashicorp/random"
    }
    tls = {
      source = "hashicorp/tls"
    }
    time = {
      source = "hashicorp/time"
    }
    archive = {
      source = "hashicorp/archive"
    }
    cloudinit = {
      source = "hashicorp/cloudinit"
    }
  }
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 4
  special = false
  upper   = false
}

locals {
  prefix  = "${var.project}-${var.environment}"
  compact = "${var.project}${var.environment}"
  suffix  = random_string.suffix.result
  tags = merge(
    {
      project     = var.project
      environment = var.environment
      managed_by  = "terraform"
    },
    var.tags
  )

  network_action = var.lock_public_access ? "Deny" : "Allow"
  network_ips    = compact([var.deployer_ip])
}

# Garde-fous : un verrouillage mal configure couperait l'acces de Terraform lui-meme.
resource "terraform_data" "guards" {
  lifecycle {
    precondition {
      condition     = !var.lock_public_access || var.enable_private_endpoints
      error_message = "lock_public_access exige enable_private_endpoints : sans lui, la VM perdrait l'acces au Key Vault et au Storage."
    }
    precondition {
      condition     = !var.lock_public_access || var.deployer_ip != ""
      error_message = "lock_public_access exige deployer_ip : sans lui, Terraform ne pourrait plus ecrire dans le Key Vault ni le Storage."
    }
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags

  depends_on = [terraform_data.guards]
}

resource "azurerm_user_assigned_identity" "vm" {
  name                = "id-${local.prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "tls_private_key" "vm" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

module "network" {
  source                   = "../network"
  name_prefix              = local.prefix
  location                 = azurerm_resource_group.this.location
  resource_group_name      = azurerm_resource_group.this.name
  allowed_ip               = var.allowed_ip
  enable_ssh               = var.enable_ssh
  enable_https             = var.enable_https
  enable_private_endpoints = var.enable_private_endpoints
  tags                     = local.tags
}

module "storage" {
  source                 = "../storage"
  name                   = "st${local.compact}${local.suffix}"
  location               = azurerm_resource_group.this.location
  resource_group_name    = azurerm_resource_group.this.name
  app_source_dir         = var.app_source_dir
  backup_retention_days  = var.backup_retention_days
  network_default_action = local.network_action
  network_ip_rules       = local.network_ips
  tags                   = local.tags
}

module "keyvault" {
  source                 = "../keyvault"
  name                   = "kv-${local.prefix}-${local.suffix}"
  location               = azurerm_resource_group.this.location
  resource_group_name    = azurerm_resource_group.this.name
  tenant_id              = data.azurerm_client_config.current.tenant_id
  deployer_object_id     = data.azurerm_client_config.current.object_id
  reader_principal_id    = azurerm_user_assigned_identity.vm.principal_id
  ssh_private_key        = tls_private_key.vm.private_key_openssh
  notify_webhook_url     = var.notify_webhook_url
  network_default_action = local.network_action
  network_ip_rules       = local.network_ips
  tags                   = local.tags
}

module "private_endpoints" {
  count               = var.enable_private_endpoints ? 1 : 0
  source              = "../private_endpoints"
  name_prefix         = local.prefix
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  vnet_id             = module.network.vnet_id
  subnet_id           = module.network.private_endpoints_subnet_id
  key_vault_id        = module.keyvault.id
  storage_account_id  = module.storage.id
  tags                = local.tags
}

resource "azurerm_role_assignment" "vm_blob" {
  scope                = module.storage.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.vm.principal_id
}

# Permet a la VM de creer et supprimer les snapshots de son disque de donnees, rien d'autre.
resource "azurerm_role_assignment" "vm_snapshots" {
  count                = var.enable_disk_snapshots ? 1 : 0
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Disk Snapshot Contributor"
  principal_id         = azurerm_user_assigned_identity.vm.principal_id
}

# Laisse le temps aux role assignments de se propager avant le premier boot de la VM.
resource "time_sleep" "rbac" {
  depends_on      = [azurerm_role_assignment.vm_blob, azurerm_role_assignment.vm_snapshots, module.keyvault]
  create_duration = "60s"
}

module "compute" {
  source                 = "../compute"
  name_prefix            = local.prefix
  environment            = var.environment
  location               = azurerm_resource_group.this.location
  resource_group_name    = azurerm_resource_group.this.name
  subnet_id              = module.network.subnet_id
  vm_size                = var.vm_size
  admin_username         = var.admin_username
  ssh_public_key         = tls_private_key.vm.public_key_openssh
  identity_id            = azurerm_user_assigned_identity.vm.id
  identity_client_id     = azurerm_user_assigned_identity.vm.client_id
  storage_account_name   = module.storage.name
  artifact_container     = module.storage.artifact_container
  artifact_blob          = module.storage.artifact_blob
  key_vault_name         = module.keyvault.name
  coins                  = var.coins
  data_disk_gb           = var.data_disk_gb
  auto_shutdown_time     = var.auto_shutdown_time
  auto_shutdown_timezone = var.auto_shutdown_timezone
  dns_label              = "${local.prefix}-${local.suffix}"
  enable_https           = var.enable_https
  enable_logging         = var.enable_logging
  acme_email             = var.alert_email
  enable_disk_snapshots  = var.enable_disk_snapshots
  snapshot_retention     = var.snapshot_retention
  tags                   = local.tags

  depends_on = [time_sleep.rbac, module.private_endpoints]
}

module "monitoring" {
  source                    = "../monitoring"
  name_prefix               = local.prefix
  environment               = var.environment
  location                  = azurerm_resource_group.this.location
  resource_group_name       = azurerm_resource_group.this.name
  vm_id                     = module.compute.vm_id
  key_vault_id              = module.keyvault.id
  alert_email               = var.alert_email
  enable_availability_alert = var.auto_shutdown_time == ""
  tags                      = local.tags
}

module "autostart" {
  count               = var.auto_start_time != "" && var.auto_shutdown_time != "" ? 1 : 0
  source              = "../autostart"
  name_prefix         = local.prefix
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  vm_id               = module.compute.vm_id
  start_time          = var.auto_start_time
  timezone            = var.auto_shutdown_timezone
  tags                = local.tags
}

module "budget" {
  count             = var.monthly_budget > 0 ? 1 : 0
  source            = "../budget"
  name_prefix       = local.prefix
  resource_group_id = azurerm_resource_group.this.id
  amount            = var.monthly_budget
  contact_email     = var.alert_email
}
