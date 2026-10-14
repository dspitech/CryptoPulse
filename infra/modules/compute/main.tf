terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
    cloudinit = {
      source = "hashicorp/cloudinit"
    }
  }
}

variable "name_prefix" {
  type = string
}

variable "environment" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "vm_size" {
  type    = string
  default = "Standard_B2s"
}

variable "admin_username" {
  type    = string
  default = "cpadmin"
}

variable "ssh_public_key" {
  type = string
}

variable "identity_id" {
  type = string
}

variable "identity_client_id" {
  type = string
}

variable "storage_account_name" {
  type = string
}

variable "artifact_container" {
  type = string
}

variable "artifact_blob" {
  type = string
}

variable "key_vault_name" {
  type = string
}

variable "coins" {
  type = list(string)
}

variable "freshness_max_hours" {
  type    = number
  default = 3
}

variable "dns_label" {
  description = "Etiquette DNS de l'IP publique : <label>.<region>.cloudapp.azure.com"
  type        = string
}

variable "enable_https" {
  type    = bool
  default = true
}

variable "enable_logging" {
  type    = bool
  default = true
}

variable "acme_email" {
  description = "Adresse de contact pour les certificats Let's Encrypt"
  type        = string
}

variable "enable_disk_snapshots" {
  type    = bool
  default = true
}

variable "snapshot_retention" {
  description = "Nombre de snapshots hebdomadaires du disque de donnees conserves"
  type        = number
  default     = 4
}

variable "os_disk_gb" {
  type    = number
  default = 64
}

variable "data_disk_gb" {
  type    = number
  default = 32
}

variable "auto_shutdown_time" {
  description = "Heure d'extinction automatique au format HHMM (vide pour desactiver)"
  type        = string
  default     = ""
}

variable "auto_shutdown_timezone" {
  type    = string
  default = "UTC"
}

variable "tags" {
  type    = map(string)
  default = {}
}

data "cloudinit_config" "this" {
  gzip          = true
  base64_encode = true

  part {
    content_type = "text/cloud-config"
    content = templatefile("${path.module}/cloud-init.yaml.tftpl", {
      environment           = var.environment
      storage_account_name  = var.storage_account_name
      key_vault_name        = var.key_vault_name
      identity_client_id    = var.identity_client_id
      artifact_container    = var.artifact_container
      artifact_blob         = var.artifact_blob
      coins                 = join(",", var.coins)
      freshness_max_hours   = var.freshness_max_hours
      enable_https          = var.enable_https
      enable_logging        = var.enable_logging
      public_fqdn           = azurerm_public_ip.this.fqdn
      acme_email            = var.acme_email
      data_disk_id          = azurerm_managed_disk.data.id
      enable_disk_snapshots = var.enable_disk_snapshots
      snapshot_retention    = var.snapshot_retention
      sync_script           = indent(6, file("${path.module}/scripts/cryptopulse-sync.sh"))
    })
  }
}

resource "azurerm_public_ip" "this" {
  name                = "pip-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = var.dns_label
  tags                = var.tags
}

resource "azurerm_network_interface" "this" {
  name                = "nic-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.subnet_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.this.id
  }
}

resource "azurerm_linux_virtual_machine" "this" {
  name                            = "vm-${var.name_prefix}"
  location                        = var.location
  resource_group_name             = var.resource_group_name
  size                            = var.vm_size
  admin_username                  = var.admin_username
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.this.id]
  custom_data                     = data.cloudinit_config.this.rendered
  tags                            = var.tags

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  os_disk {
    name                 = "osdisk-${var.name_prefix}"
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = var.os_disk_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  boot_diagnostics {}
}

resource "azurerm_managed_disk" "data" {
  name                 = "disk-data-${var.name_prefix}"
  location             = var.location
  resource_group_name  = var.resource_group_name
  storage_account_type = "StandardSSD_LRS"
  create_option        = "Empty"
  disk_size_gb         = var.data_disk_gb
  tags                 = var.tags
}

resource "azurerm_virtual_machine_data_disk_attachment" "data" {
  managed_disk_id    = azurerm_managed_disk.data.id
  virtual_machine_id = azurerm_linux_virtual_machine.this.id
  lun                = 0
  caching            = "ReadWrite"
}

resource "azurerm_dev_test_global_vm_shutdown_schedule" "this" {
  count                 = var.auto_shutdown_time == "" ? 0 : 1
  virtual_machine_id    = azurerm_linux_virtual_machine.this.id
  location              = var.location
  enabled               = true
  daily_recurrence_time = var.auto_shutdown_time
  timezone              = var.auto_shutdown_timezone

  notification_settings {
    enabled = false
  }
}

output "public_ip" {
  value = azurerm_public_ip.this.ip_address
}

output "fqdn" {
  value = azurerm_public_ip.this.fqdn
}

output "data_disk_id" {
  value = azurerm_managed_disk.data.id
}

output "vm_id" {
  value = azurerm_linux_virtual_machine.this.id
}

output "vm_name" {
  value = azurerm_linux_virtual_machine.this.name
}
