locals {
  host   = var.enable_https ? module.compute.fqdn : module.compute.public_ip
  scheme = var.enable_https ? "https" : "http"
  ports = {
    grafana   = var.enable_https ? "" : ":3000"
    airflow   = var.enable_https ? ":8443" : ":8080"
    dashboard = var.enable_https ? ":9443" : ":8501"
    api       = var.enable_https ? ":8444" : ":8000"
  }
}

output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "vm_public_ip" {
  value = module.compute.public_ip
}

output "fqdn" {
  value = module.compute.fqdn
}

output "grafana_url" {
  value = "${local.scheme}://${local.host}${local.ports.grafana}"
}

output "airflow_url" {
  value = "${local.scheme}://${local.host}${local.ports.airflow}"
}

output "dashboard_url" {
  value = "${local.scheme}://${local.host}${local.ports.dashboard}"
}

output "api_url" {
  value = "${local.scheme}://${local.host}${local.ports.api}"
}

output "api_docs_url" {
  value = "${local.scheme}://${local.host}${local.ports.api}/docs"
}

output "ssh_command" {
  value = "ssh -i ~/.ssh/${local.prefix} ${var.admin_username}@${module.compute.public_ip}"
}

output "key_vault_name" {
  value = module.keyvault.name
}

output "storage_account_name" {
  value = module.storage.name
}
