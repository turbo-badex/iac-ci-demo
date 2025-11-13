terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "my-terraform-state-dev-badex" # <-- your bucket name
    key            = "infra/terraform.tfstate"      # path inside the bucket
    region         = "us-east-1"                    # must match bucket region
    dynamodb_table = "terraform-locks-dev"          # lock table name
    encrypt        = true
  }
}


provider "aws" {
  region = "us-east-1"
}

variable "logs_bucket_name" {
  type        = string
  description = "Name of the S3 bucket for logs"
}

# KMSs keys for encrypting the S3 bucket by default (for CKV_AWS_145)
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
    Name        = "logs-bucket"
    Environment = "dev"
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

# Encrypt objects at rest with KMS by default (CKV_AWS_145)
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