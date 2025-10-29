variable "region" {
  description = "AWS region for Papyrus"
  type        = string
}

variable "cluster_name" {
  description = "ECS ClusterName used in CloudWatch dimensions"
  type        = string
}

variable "service_name" {
  description = "ECS ServiceName used in CloudWatch dimensions"
  type        = string
}

variable "alb_arn_suffix" {
  description = "ALB ARN suffix for metrics (like app/papyrus-alb/xxxxxxxxxxxx)"
  type        = string
}

variable "tg_arn_suffix" {
  description = "TargetGroup ARN suffix for metrics (like targetgroup/papyrus-tg/xxxxxxxxxxxx)"
  type        = string
}

variable "topic_name" {
  description = "SNS topic to push alarms to (will be created if not exists)"
  type        = string
  default     = "papyrus-ops-alerts"
}
