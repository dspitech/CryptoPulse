terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
    archive = {
      source = "hashicorp/archive"
    }
  }
}

variable "name" {
  description = "Nom du storage account (minuscules, max 24 caracteres)"
  type        = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "app_source_dir" {
  description = "Dossier app/ a empaqueter et publier comme artefact de deploiement"
  type        = string
}

variable "network_default_action" {
  description = "Allow (defaut) ou Deny : en Deny, seuls ip_rules et les Private Endpoints peuvent acceder au compte"
  type        = string
  default     = "Allow"
}

variable "network_ip_rules" {
  description = "Adresses IP autorisees quand network_default_action vaut Deny (poste qui execute Terraform)"
  type        = list(string)
  default     = []
}

variable "backup_retention_days" {
  description = "Duree de conservation des sauvegardes PostgreSQL dans gold/backups/"
  type        = number
  default     = 30
}

variable "cool_after_days" {
  description = "Nombre de jours avant passage du bronze en tier Cool"
  type        = number
  default     = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  lake_containers    = ["bronze", "silver", "gold"]
  artifact_container = "artifacts"
  artifact_blob      = "app.zip"
}

resource "azurerm_storage_account" "this" {
  name                            = var.name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  enable_https_traffic_only       = true
  tags                            = var.tags

  blob_properties {
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }

  dynamic "network_rules" {
    for_each = var.network_default_action == "Deny" ? [1] : []
    content {
      default_action = "Deny"
      ip_rules       = var.network_ip_rules
      bypass         = ["AzureServices"]
    }
  }
}

resource "azurerm_storage_container" "lake" {
  for_each              = toset(local.lake_containers)
  name                  = each.key
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "artifacts" {
  name                  = local.artifact_container
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "lake" {
  storage_account_id = azurerm_storage_account.this.id

  rule {
    name    = "bronze-to-cool"
    enabled = true
    filters {
      prefix_match = ["bronze/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = var.cool_after_days
      }
    }
  }

  rule {
    name    = "expire-database-backups"
    enabled = true
    filters {
      prefix_match = ["gold/backups/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.backup_retention_days
      }
    }
  }
}

data "archive_file" "app" {
  type        = "zip"
  source_dir  = var.app_source_dir
  output_path = "${path.module}/app.zip"

  # Ne jamais publier de secrets locaux ni de fichiers de developpement.
  # Attention : dbt/tests contient des tests dbt necessaires, il ne doit pas etre exclu.
  excludes = [
    "deploy/.env.local",
    "deploy/docker-compose.local.yml",
    "deploy/local/**",
    "ingestion/tests/**",
    "ingestion/pytest.ini",
    "api/tests/**",
    "api/pytest.ini",
    "airflow/tests/**",
    "airflow/pytest.ini",
    "dbt/target/**",
    "dbt/logs/**",
    "dbt/dbt_packages/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/*.pyc",
  ]
}

resource "azurerm_storage_blob" "app" {
  name                   = local.artifact_blob
  storage_account_name   = azurerm_storage_account.this.name
  storage_container_name = azurerm_storage_container.artifacts.name
  type                   = "Block"
  source                 = data.archive_file.app.output_path
  content_md5            = data.archive_file.app.output_md5
}

output "id" {
  value = azurerm_storage_account.this.id
}

output "name" {
  value = azurerm_storage_account.this.name
}

output "artifact_container" {
  value = azurerm_storage_container.artifacts.name
}

output "artifact_blob" {
  value = azurerm_storage_blob.app.name
}
