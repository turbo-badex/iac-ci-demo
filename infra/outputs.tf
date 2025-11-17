# outputs.tf

# Name of the logs bucket (useful for debugging or wiring to other tools)
output "logs_bucket_name" {
  description = "Name of the S3 bucket for logs"
  value       = aws_s3_bucket.logs.id
}

# ARN of the KMS key used to encrypt the logs bucket
output "logs_kms_key_arn" {
  description = "ARN of the KMS key for the logs bucket"
  value       = aws_kms_key.logs.arn
}