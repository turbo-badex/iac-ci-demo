output "dev_bastion_public_ip" {
  description = "Public IP of the dev bastion host"
  value       = local.is_dev && length(aws_instance.dev_bastion) > 0 ? aws_instance.dev_bastion[0].public_ip : null
}

output "dev_rds_endpoint" {
  description = "Endpoint of the dev RDS PostgreSQL instance"
  value       = local.is_dev && length(aws_db_instance.dev_postgres) > 0 ? aws_db_instance.dev_postgres[0].address : null
}

output "dev_rds_db_name" {
  description = "Database name on the dev RDS instance"
  value       = var.db_name
}