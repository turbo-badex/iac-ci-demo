terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

locals {
  is_dev = var.environment == "dev"
}

provider "aws" {
  region = "us-east-1"
}

variable "logs_bucket_name" {
  type        = string
  description = "Name of the S3 bucket for logs"
}

# KMSs keyss for encrypting the S3 bucket by default (fore CKV_AWS_145)
data "aws_caller_identity" "current" {}
resource "aws_kms_key" "logs" {
  description             = "KMS key for S3 logs bucket"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      }
    ]
  })
}

# Main S3 bucket resource
resource "aws_s3_bucket" "logs" {
  bucket = var.logs_bucket_name

  # We are deliberately skipping some Checkov rules that are not needed
  # for this training bucket (e.g., event notifications, cross-region replication).
  # checkov:skip=CKV2_AWS_62: Event notifications are not required for this training bucket
  # checkov:skip=CKV_AWS_144: Cross-region replication is not required for this training bucket

  tags = {
    Name        = "logs-bucket-${var.environment}"
    Environment = var.environment
  }
}

# Block all public access to this bucket (CKV2_AWS_6)
resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable versioning (CKV_AWS_21)
resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Encrypt objects at rest withh KMS by default (CKV_AWS_145)
resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.logs.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

# Enable server access logging for the bucket (CKV_AWS_18)
# In a real setup, logs usually go to a separate bucket.
resource "aws_s3_bucket_logging" "logs" {
  bucket = aws_s3_bucket.logs.id

  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "access-logs/"
}

# Lifecycles configuration (CKV2_AWS_61)
resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "logs-retention"
    status = "Enabled"

    expiration {
      days = 365
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Data source: Default VPC & Subnets
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security Groups for Bastion & RDS

resource "aws_security_group" "bastion" {
  count       = local.is_dev ? 1 : 0
  name        = "dev-bastion-sg"
  description = "Security group for bastion host (dev)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from allowed CIDR"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "dev-bastion-sg"
    Environment = var.environment
  }
}

resource "aws_security_group" "rds" {
  count       = local.is_dev ? 1 : 0
  name        = "dev-rds-sg"
  description = "Security group for RDS PostgreSQL (dev)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description      = "PostgreSQL from bastion host"
    from_port        = 5432
    to_port          = 5432
    protocol         = "tcp"
    security_groups  = [aws_security_group.bastion[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "dev-rds-sg"
    Environment = var.environment
  }
}

# DB Subnet Group for RDS
resource "aws_db_subnet_group" "dev" {
  count       = local.is_dev ? 1 : 0
  name        = "dev-rds-subnet-group"
  description = "Subnet group for dev RDS instance"
  subnet_ids  = data.aws_subnets.default.ids

  tags = {
    Name        = "dev-rds-subnet-group"
    Environment = var.environment
  }
}

# Create the RDS PostgreSQL Instance (Dev Only)
resource "aws_db_instance" "dev_postgres" {
  count = local.is_dev ? 1 : 0

  identifier        = "dev-postgres-${var.environment}"
  engine            = "postgres"
  engine_version    = "16.1"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = var.db_name
  username = var.db_username

  # Let AWS manage the master user password in Secrets Manager.
  # This avoids hardcoding or passing the password in tfvars for now.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.dev[0].name
  vpc_security_group_ids = [aws_security_group.rds[0].id]

  publicly_accessible = false
  skip_final_snapshot = true  # OK for dev. In prod you'd set this to false.

  backup_retention_period = 1

  deletion_protection = false

  tags = {
    Name        = "dev-postgres-${var.environment}"
    Environment = var.environment
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true

  owners = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-*-20.04-amd64-server-*"]
  }
}

resource "aws_instance" "dev_bastion" {
  count = local.is_dev ? 1 : 0

  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"

  key_name = var.bastion_key_name

  vpc_security_group_ids = [aws_security_group.bastion[0].id]
  subnet_id              = data.aws_subnets.default.ids[0]

  associate_public_ip_address = true

  tags = {
    Name        = "dev-bastion-${var.environment}"
    Environment = var.environment
  }
}

