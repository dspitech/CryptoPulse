variable "project" {
  description = "Nom du projet"
  type        = string
  default     = "cryptopulse"
}

variable "environment" {
  description = "Environnement (dev, prod)"
  type        = string
}

variable "location" {
  description = "Region Azure"
  type        = string
  default     = "norwayeast"
}

variable "allowed_ip" {
  description = "IP publique autorisee a acceder a Airflow, au dashboard et a SSH"
  type        = string

  validation {
    condition     = can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$", var.allowed_ip))
    error_message = "allowed_ip doit etre une adresse IPv4 au format x.x.x.x."
  }
}

variable "alert_email" {
  description = "Adresse email qui recoit les alertes Azure Monitor"
  type        = string
}

variable "vm_size" {
  type    = string
  default = "Standard_B2s"
}

variable "admin_username" {
  type    = string
  default = "cpadmin"
}

variable "coins" {
  description = "Identifiants CoinGecko des cryptomonnaies suivies"
  type        = list(string)
  default     = ["bitcoin", "ethereum", "solana", "cardano", "ripple"]
}

variable "enable_ssh" {
  description = "Ouvre le port 22 depuis allowed_ip"
  type        = bool
  default     = true
}

variable "data_disk_gb" {
  type    = number
  default = 32
}

variable "auto_shutdown_time" {
  description = "Extinction automatique quotidienne au format HHMM, vide pour desactiver"
  type        = string
  default     = ""
}

variable "auto_shutdown_timezone" {
  type    = string
  default = "UTC"
}

variable "app_source_dir" {
  description = "Chemin du dossier app/ du depot"
  type        = string
}

variable "enable_https" {
  description = "Publie Airflow, Grafana, le dashboard et l'API en HTTPS (Caddy et Let's Encrypt)"
  type        = bool
  default     = true
}

variable "enable_logging" {
  description = "Deploie Loki et Promtail (logs des conteneurs dans Grafana). Consomme environ 400 Mo de RAM."
  type        = bool
  default     = true
}

variable "enable_private_endpoints" {
  description = "Cree des Private Endpoints pour le Key Vault et le Storage (environ 15 USD par mois)"
  type        = bool
  default     = false
}

variable "lock_public_access" {
  description = "Interdit l'acces public au Key Vault et au Storage (necessite enable_private_endpoints et deployer_ip)"
  type        = bool
  default     = false
}

variable "deployer_ip" {
  description = "IP publique fixe du poste qui execute Terraform, requise si lock_public_access est actif"
  type        = string
  default     = ""
}

variable "auto_start_time" {
  description = "Demarrage automatique quotidien de la VM au format HHMM (vide pour desactiver)"
  type        = string
  default     = ""
}

variable "monthly_budget" {
  description = "Budget mensuel du resource group dans la devise de facturation (0 pour desactiver)"
  type        = number
  default     = 0
}

variable "enable_disk_snapshots" {
  description = "Snapshot hebdomadaire incremental du disque de donnees"
  type        = bool
  default     = true
}

variable "snapshot_retention" {
  type    = number
  default = 4
}

variable "backup_retention_days" {
  description = "Duree de conservation des sauvegardes PostgreSQL dans le Data Lake"
  type        = number
  default     = 30
}

variable "notify_webhook_url" {
  description = "Webhook de notification (optionnel). A fournir via TF_VAR_notify_webhook_url."
  type        = string
  sensitive   = true
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
