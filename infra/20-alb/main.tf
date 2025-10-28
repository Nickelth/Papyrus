terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "local" {
    # state を /tmp に隔離（容量対策）
    path = "/tmp/tfstate-20alb.tfstate"
  }
}

variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "container_port" { 
  type = number
  default = 5000 
}
variable "allow_cidrs" { 
  type = list(string)
  default = ["0.0.0.0/0"] 
}
variable "ecs_tasks_sg_id" {
  type = string
  default = null
}

resource "aws_security_group" "alb" {
  name        = "papyrus-alb-sg"
  description = "ALB SG"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from allowed CIDRs"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allow_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_to_tasks_5000" {
  count = var.ecs_tasks_sg_id == null ? 0 : 1
  security_group_id            = var.ecs_tasks_sg_id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
  description                  = "ALB to ECS task 5000"
}

resource "aws_lb" "this" {
  name                       = "papyrus-alb"
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = var.public_subnet_ids
  idle_timeout               = 30
  enable_deletion_protection = false
}

resource "aws_lb_target_group" "this" {
  name                 = "papyrus-tg"
  port                 = var.container_port
  protocol             = "HTTP"
  vpc_id               = var.vpc_id
  target_type          = "ip"
  deregistration_delay = 15

  health_check {
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 10
    timeout             = 5
    path                = "/"
    matcher             = "200-399"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}
