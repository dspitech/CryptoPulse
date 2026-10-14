project      = "cryptopulse"
environment  = "dev"
location     = "norwayeast"
vm_size      = "Standard_B2s"
coins        = ["bitcoin", "ethereum", "solana", "cardano", "ripple"]
enable_ssh   = true
data_disk_gb = 32
alert_email  = "you@example.com"

# Cout : la VM s'eteint a 21h00 UTC et redemarre seule a 07h00 UTC
auto_shutdown_time     = "2100"
auto_shutdown_timezone = "UTC"
auto_start_time        = "0700"

# Fonctionnalites
enable_https          = true
enable_logging        = true
enable_disk_snapshots = true
snapshot_retention    = 4
backup_retention_days = 30

# Securite reseau : activer ensemble avec une IP fixe pour le poste qui execute Terraform
enable_private_endpoints = false
lock_public_access       = false
deployer_ip              = ""

# Budget mensuel (0 = desactive). Mettre par exemple 40 pour activer l'alerte de cout.
monthly_budget = 0
