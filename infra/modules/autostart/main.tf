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

variable "vm_id" {
  type = string
}

variable "start_time" {
  description = "Heure de demarrage quotidien au format HHMM"
  type        = string

  validation {
    condition     = can(regex("^([01][0-9]|2[0-3])[0-5][0-9]$", var.start_time))
    error_message = "start_time doit etre au format HHMM, par exemple 0700."
  }
}

variable "timezone" {
  type    = string
  default = "UTC"
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  hour   = tonumber(substr(var.start_time, 0, 2))
  minute = tonumber(substr(var.start_time, 2, 2))
}

# Logic App Consommation : cout negligeable, une execution par jour.
resource "azurerm_logic_app_workflow" "start_vm" {
  name                = "logic-${var.name_prefix}-autostart"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_role_assignment" "start_vm" {
  scope                = var.vm_id
  role_definition_name = "Virtual Machine Contributor"
  principal_id         = azurerm_logic_app_workflow.start_vm.identity[0].principal_id
}

resource "azurerm_logic_app_trigger_recurrence" "daily" {
  name         = "daily-start"
  logic_app_id = azurerm_logic_app_workflow.start_vm.id
  frequency    = "Day"
  interval     = 1
  time_zone    = var.timezone

  schedule {
    at_these_hours   = [local.hour]
    at_these_minutes = [local.minute]
  }
}

resource "azurerm_logic_app_action_custom" "start_vm" {
  name         = "start-vm"
  logic_app_id = azurerm_logic_app_workflow.start_vm.id

  body = jsonencode({
    type = "Http"
    inputs = {
      method = "POST"
      uri    = "https://management.azure.com${var.vm_id}/start?api-version=2024-03-01"
      authentication = {
        type     = "ManagedServiceIdentity"
        audience = "https://management.azure.com/"
      }
    }
    runAfter = {}
  })

  depends_on = [azurerm_role_assignment.start_vm]
}
