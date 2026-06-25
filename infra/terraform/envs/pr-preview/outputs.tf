output "lambda_backend" {
  description = "Isolated PR preview Lambda backend metadata and direct endpoint."
  value = {
    preview_id       = local.preview_id
    function_name    = module.lambda_backend.function_name
    alias_name       = module.lambda_backend.alias_name
    state_table_name = module.lambda_backend.state_table_name
    state_key_prefix = local.preview_id
    invoke_url       = module.lambda_backend.invoke_url
    log_group_name   = module.lambda_backend.log_group_name
    expiration_at    = var.expiration_at
  }
}
