terraform {
  required_version = ">= 1.5.0"

  backend "azurerm" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.11"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.11"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "~> 2.3"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

module "platform" {
  source = "../../modules/platform"

  project                  = var.project
  environment              = var.environment
  location                 = var.location
  allowed_ip               = var.allowed_ip
  alert_email              = var.alert_email
  vm_size                  = var.vm_size
  coins                    = var.coins
  enable_ssh               = var.enable_ssh
  data_disk_gb             = var.data_disk_gb
  auto_shutdown_time       = var.auto_shutdown_time
  auto_shutdown_timezone   = var.auto_shutdown_timezone
  enable_https             = var.enable_https
  enable_logging           = var.enable_logging
  enable_private_endpoints = var.enable_private_endpoints
  lock_public_access       = var.lock_public_access
  deployer_ip              = var.deployer_ip
  auto_start_time          = var.auto_start_time
  monthly_budget           = var.monthly_budget
  enable_disk_snapshots    = var.enable_disk_snapshots
  snapshot_retention       = var.snapshot_retention
  backup_retention_days    = var.backup_retention_days
  notify_webhook_url       = var.notify_webhook_url
  app_source_dir           = "${path.module}/../../../app"
}
