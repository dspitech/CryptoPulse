project      = "cryptopulse"
environment  = "prod"
location     = "norwayeast"
vm_size      = "Standard_B2s"
coins        = ["bitcoin", "ethereum", "solana", "cardano", "ripple", "dogecoin", "polkadot"]
enable_ssh   = false
data_disk_gb = 64
alert_email  = "you@example.com"

auto_shutdown_time     = ""
auto_shutdown_timezone = "UTC"
auto_start_time        = ""

enable_https          = true
enable_logging        = true
enable_disk_snapshots = true
snapshot_retention    = 4
backup_retention_days = 90

enable_private_endpoints = true
lock_public_access       = false
deployer_ip              = ""

monthly_budget = 0
