variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "location" {
  type = string
}

variable "vm_size" {
  type = string
}

variable "coins" {
  type = list(string)
}

variable "enable_ssh" {
  type = bool
}

variable "data_disk_gb" {
  type = number
}

variable "auto_shutdown_time" {
  type = string
}

variable "auto_shutdown_timezone" {
  type = string
}

variable "enable_https" {
  description = "Publie les services en HTTPS (Caddy)"
  type        = bool
}

variable "enable_logging" {
  description = "Deploie Loki et Promtail"
  type        = bool
}

variable "enable_private_endpoints" {
  description = "Private Endpoints pour Key Vault et Storage"
  type        = bool
}

variable "lock_public_access" {
  description = "Interdit l'acces public au Key Vault et au Storage"
  type        = bool
}

variable "deployer_ip" {
  description = "IP fixe du poste qui execute Terraform (requise avec lock_public_access)"
  type        = string
}

variable "auto_start_time" {
  description = "Demarrage automatique quotidien HHMM, vide pour desactiver"
  type        = string
}

variable "monthly_budget" {
  description = "Budget mensuel, 0 pour desactiver"
  type        = number
}

variable "enable_disk_snapshots" {
  description = "Snapshot hebdomadaire du disque de donnees"
  type        = bool
}

variable "snapshot_retention" {
  description = "Nombre de snapshots conserves"
  type        = number
}

variable "backup_retention_days" {
  description = "Conservation des sauvegardes PostgreSQL en jours"
  type        = number
}

variable "notify_webhook_url" {
  description = "Webhook de notification optionnel, via TF_VAR_notify_webhook_url"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alert_email" {
  type = string
}

variable "allowed_ip" {
  description = "Fournie par le Makefile (ALLOWED_IP)"
  type        = string
}
