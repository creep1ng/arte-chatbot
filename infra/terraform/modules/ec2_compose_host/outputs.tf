output "instance_id" {
  description = "EC2 Compose host instance id for SSM deploy targeting."
  value       = aws_instance.this.id
}

output "instance_role_arn" {
  description = "IAM role ARN used by the EC2 Compose host."
  value       = aws_iam_role.this.arn
}

output "security_group_id" {
  description = "Outbound-only EC2 host security group id."
  value       = aws_security_group.this.id
}

output "deploy_script_path" {
  description = "Path invoked by SSM Run Command for application deploys."
  value       = "/opt/arte-chatbot/deploy.sh"
}

output "compose_project_directory" {
  description = "Directory containing Docker Compose assets on the host."
  value       = "/opt/arte-chatbot"
}
