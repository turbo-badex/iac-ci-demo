variable "environment" {
  type        = string
  description = "Deployment environment name (e.g. dev, staging, prod)"
}

variable "db_name" {
  type        = string
  description = "PostgreSQL database name for the app"
  default     = "app_db"
}

variable "db_username" {
  type        = string
  description = "Master username for PostgreSQL"
  default     = "app_admin"
}

variable "bastion_key_name" {
  type        = string
  description = "Name of the existing EC2 key pair to use for the bastion host"
}

variable "allowed_ssh_cidr" {
  type        = string
  description = "CIDR block allowed to SSH into the bastion (e.g. your public IP/32)"
  default     = "0.0.0.0/0" # OK for learning, but in real life use your_IP/32
}