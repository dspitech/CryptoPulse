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

variable "resource_group_id" {
  type = string
}

variable "amount" {
  description = "Budget mensuel dans la devise de facturation de l'abonnement"
  type        = number
}

variable "contact_email" {
  type = string
}

locals {
  # Un budget doit commencer le premier jour d'un mois.
  start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp())
}

resource "azurerm_consumption_budget_resource_group" "this" {
  name              = "budget-${var.name_prefix}"
  resource_group_id = var.resource_group_id
  amount            = var.amount
  time_grain        = "Monthly"

  time_period {
    start_date = local.start_date
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.contact_email]
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.contact_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.contact_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.contact_email]
  }

  lifecycle {
    # timestamp() change a chaque plan : la date de debut ne doit pas provoquer de remplacement.
    ignore_changes = [time_period]
  }
}
