locals {
  secret_base_path = "/${var.name_prefix}/${var.environment}/secrets"
  param_base_path  = "/${var.name_prefix}/${var.environment}/params"

  secret_keys = toset(keys(nonsensitive(var.secrets)))
  param_keys  = toset(keys(nonsensitive(var.ssm_parameters)))
}

resource "aws_secretsmanager_secret" "this" {
  for_each = local.secret_keys

  name        = "${local.secret_base_path}/${each.key}"
  description = var.secrets[each.key].description
  tags        = var.tags
}

resource "aws_secretsmanager_secret_version" "this" {
  for_each = local.secret_keys

  secret_id     = aws_secretsmanager_secret.this[each.key].id
  secret_string = var.secrets[each.key].value
}

resource "aws_ssm_parameter" "this" {
  for_each = local.param_keys

  name        = "${local.param_base_path}/${each.key}"
  description = var.ssm_parameters[each.key].description
  type        = var.ssm_parameters[each.key].secure ? "SecureString" : "String"
  value       = var.ssm_parameters[each.key].value
  tags        = var.tags
}
