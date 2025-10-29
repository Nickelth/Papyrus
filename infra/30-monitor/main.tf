terraform {
  required_version = ">= 1.7.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.18.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# 監視通知用のSNSトピック (slack連携でもメールでも電話でも勝手にやれ)
resource "aws_sns_topic" "ops" {
  name = var.topic_name
}

# 必要なら購読は別リソースで足す:
# resource "aws_sns_topic_subscription" "ops_email" {
#   topic_arn = aws_sns_topic.ops.arn
#   protocol  = "email"
#   endpoint  = "you@example.com"
# }

########################################
# 1. ECS メモリ使用率 > 80%
########################################
resource "aws_cloudwatch_metric_alarm" "ecs_mem_hi" {
  alarm_name          = "papyrus-ecs-mem-gt80"
  alarm_description   = "ECS service memory >80% (papyrus ${var.service_name})"
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  statistic           = "Average"

  comparison_operator = "GreaterThanThreshold"
  threshold           = 80

  evaluation_periods  = 2
  period              = 300  # 5分
  treat_missing_data  = "breaching"

  dimensions = {
    ClusterName = var.cluster_name
    ServiceName = var.service_name
  }

  alarm_actions = [aws_sns_topic.ops.arn]
  ok_actions    = [aws_sns_topic.ops.arn]
}

########################################
# 2. ALB 5xx が出てる
########################################
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name        = "papyrus-alb-5xx-gt1"
  alarm_description = "ALB is serving 5xx > 1 in 5 min window"

  namespace   = "AWS/ApplicationELB"
  metric_name = "HTTPCode_ELB_5XX_Count"
  statistic   = "Sum"

  comparison_operator = "GreaterThanThreshold"
  threshold           = 1
  evaluation_periods  = 2
  period              = 300
  treat_missing_data  = "notBreaching"

  # CloudWatchはALB/ターゲットグループを dimensions に arn_suffix で食わせるクソ仕様
  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = [aws_sns_topic.ops.arn]
  ok_actions    = [aws_sns_topic.ops.arn]
}

########################################
# 3. レイテンシが遅すぎる (p90 > 1.5秒)
########################################
resource "aws_cloudwatch_metric_alarm" "alb_latency" {
  alarm_name        = "papyrus-alb-p90-gt1_5s"
  alarm_description = "TargetResponseTime p90 > 1.5s (bad latency)"

  namespace          = "AWS/ApplicationELB"
  metric_name        = "TargetResponseTime"
  extended_statistic = "p90"

  comparison_operator = "GreaterThanThreshold"
  threshold           = 1.5
  evaluation_periods  = 2
  period              = 300
  treat_missing_data  = "notBreaching"

  dimensions = {
    TargetGroup  = var.tg_arn_suffix
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = [aws_sns_topic.ops.arn]
  ok_actions    = [aws_sns_topic.ops.arn]
}
