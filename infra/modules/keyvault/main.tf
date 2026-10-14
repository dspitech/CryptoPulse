terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
    random = {
      source = "hashicorp/random"
    }
    time = {
      source = "hashicorp/time"
    }
  }
}

variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "tenant_id" {
  type = string
}

variable "deployer_object_id" {
  description = "Object ID de l'identite qui execute Terraform (ecriture des secrets)"
  type        = string
}

variable "reader_principal_id" {
  description = "Principal ID de l'identite managee de la VM (lecture des secrets)"
  type        = string
}

variable "ssh_private_key" {
  description = "Cle privee SSH generee par Terraform"
  type        = string
  sensitive   = true
}

variable "notify_webhook_url" {
  description = "URL de webhook pour les notifications Airflow et Alertmanager (optionnel)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "network_default_action" {
  description = "Allow (defaut) ou Deny : en Deny, seuls ip_rules et les Private Endpoints peuvent acceder au coffre"
  type        = string
  default     = "Allow"
}

variable "network_ip_rules" {
  description = "Adresses IP autorisees quand network_default_action vaut Deny (poste qui execute Terraform)"
  type        = list(string)
  default     = []
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "azurerm_key_vault" "this" {
  name                       = var.name
  location                   = var.location
  resource_group_name        = var.resource_group_name
  tenant_id                  = var.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = var.tags

  dynamic "network_acls" {
    for_each = var.network_default_action == "Deny" ? [1] : []
    content {
      default_action = "Deny"
      bypass         = "AzureServices"
      ip_rules       = var.network_ip_rules
    }
  }
}

resource "azurerm_role_assignment" "deployer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = var.deployer_object_id
}

resource "azurerm_role_assignment" "reader" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.reader_principal_id
}

# Les role assignments RBAC mettent un moment a se propager.
resource "time_sleep" "rbac" {
  depends_on      = [azurerm_role_assignment.deployer, azurerm_role_assignment.reader]
  create_duration = "60s"
}

resource "random_password" "postgres" {
  length  = 28
  special = false
}

resource "random_password" "airflow_admin" {
  length  = 24
  special = false
}

resource "random_password" "grafana_admin" {
  length  = 24
  special = false
}

resource "random_password" "monitoring_db" {
  length  = 28
  special = false
}

resource "random_password" "api_db" {
  length  = 28
  special = false
}

resource "random_password" "api_key" {
  length  = 40
  special = false
}

resource "random_id" "airflow_secret_key" {
  byte_length = 32
}

resource "random_id" "airflow_fernet" {
  byte_length = 32
}

resource "azurerm_key_vault_secret" "postgres" {
  name         = "postgres-password"
  value        = random_password.postgres.result
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

resource "azurerm_key_vault_secret" "airflow_admin" {
  name         = "airflow-admin-password"
  value        = random_password.airflow_admin.result
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

resource "azurerm_key_vault_secret" "airflow_secret_key" {
  name         = "airflow-secret-key"
  value        = random_id.airflow_secret_key.hex
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

# Une cle Fernet est une chaine base64 url-safe de 32 octets, avec padding.
resource "azurerm_key_vault_secret" "airflow_fernet" {
  name         = "airflow-fernet-key"
  value        = "${random_id.airflow_fernet.b64_url}="
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

resource "azurerm_key_vault_secret" "ssh_private_key" {
  name         = "vm-ssh-private-key"
  value        = var.ssh_private_key
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

resource "azurerm_key_vault_secret" "grafana_admin" {
  name         = "grafana-admin-password"
  value        = random_password.grafana_admin.result
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

resource "azurerm_key_vault_secret" "monitoring_db" {
  name         = "monitoring-db-password"
  value        = random_password.monitoring_db.result
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

resource "azurerm_key_vault_secret" "api_db" {
  name         = "api-db-password"
  value        = random_password.api_db.result
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

resource "azurerm_key_vault_secret" "api_key" {
  name         = "api-key"
  value        = random_password.api_key.result
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

resource "azurerm_key_vault_secret" "notify_webhook" {
  count        = nonsensitive(var.notify_webhook_url != "") ? 1 : 0
  name         = "notify-webhook-url"
  value        = var.notify_webhook_url
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [time_sleep.rbac]
}

output "id" {
  value = azurerm_key_vault.this.id
}

output "name" {
  value = azurerm_key_vault.this.name
}
