terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}

variable "name_prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "allowed_ip" {
  description = "IP publique autorisee (format x.x.x.x)"
  type        = string
}

variable "enable_ssh" {
  type    = bool
  default = true
}

variable "enable_https" {
  description = "Publie les services via Caddy en HTTPS (ports 443, 8443, 9443, 8444) au lieu de HTTP direct"
  type        = bool
  default     = true
}

variable "enable_private_endpoints" {
  description = "Cree le sous-reseau dedie aux Private Endpoints"
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  # internet = true : ouvert a tous. Reserve au port 80, indispensable au defi ACME HTTP-01 de Let's Encrypt.
  # Caddy n'y repond qu'avec le defi ou une redirection vers HTTPS.
  rules = {
    ssh           = { priority = 100, port = "22", internet = false, enabled = var.enable_ssh }
    acme          = { priority = 105, port = "80", internet = true, enabled = var.enable_https }
    airflow       = { priority = 110, port = "8080", internet = false, enabled = !var.enable_https }
    dashboard     = { priority = 120, port = "8501", internet = false, enabled = !var.enable_https }
    grafana       = { priority = 130, port = "3000", internet = false, enabled = !var.enable_https }
    api           = { priority = 135, port = "8000", internet = false, enabled = !var.enable_https }
    grafana_tls   = { priority = 140, port = "443", internet = false, enabled = var.enable_https }
    airflow_tls   = { priority = 150, port = "8443", internet = false, enabled = var.enable_https }
    dashboard_tls = { priority = 160, port = "9443", internet = false, enabled = var.enable_https }
    api_tls       = { priority = 170, port = "8444", internet = false, enabled = var.enable_https }
  }
  active_rules = { for k, v in local.rules : k => v if v.enabled }
}

resource "azurerm_virtual_network" "this" {
  name                = "vnet-${var.name_prefix}"
  address_space       = ["10.10.0.0/16"]
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_subnet" "this" {
  name                 = "snet-${var.name_prefix}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.10.1.0/24"]
}

resource "azurerm_subnet" "private_endpoints" {
  count                                     = var.enable_private_endpoints ? 1 : 0
  name                                      = "snet-${var.name_prefix}-pe"
  resource_group_name                       = var.resource_group_name
  virtual_network_name                      = azurerm_virtual_network.this.name
  address_prefixes                          = ["10.10.2.0/24"]
  private_endpoint_network_policies_enabled = false
}

resource "azurerm_network_security_group" "this" {
  name                = "nsg-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_network_security_rule" "inbound" {
  for_each                    = local.active_rules
  name                        = "allow-${replace(each.key, "_", "-")}"
  priority                    = each.value.priority
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = each.value.port
  source_address_prefix       = each.value.internet ? "Internet" : "${var.allowed_ip}/32"
  destination_address_prefix  = "*"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.this.name
}

resource "azurerm_subnet_network_security_group_association" "this" {
  subnet_id                 = azurerm_subnet.this.id
  network_security_group_id = azurerm_network_security_group.this.id
}

output "subnet_id" {
  value = azurerm_subnet.this.id
}

output "vnet_id" {
  value = azurerm_virtual_network.this.id
}

output "private_endpoints_subnet_id" {
  value = one(azurerm_subnet.private_endpoints[*].id)
}
