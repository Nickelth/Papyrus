variable "vpc_id" {}
variable "public_subnet_ids" { type = list(string) }
variable "container_port" { default = 5000 }
resource "aws_security_group" "alb" { /* 80だけ許可（CIDRは最小） */ }
resource "aws_lb" "this" { load_balancer_type = "application" /* idle_timeout=30, deletion_protection=false */ }
resource "aws_lb_target_group" "this" {
  vpc_id = var.vpc_id
  port = var.container_port
  protocol = "HTTP"
  target_type = "ip"
  deregistration_delay = 15
  health_check { 
    path="/healthz" 
    matcher="200-399" 
    interval=10 
    timeout=5 
    healthy_threshold=2 
    unhealthy_threshold=2 
    }
}
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port=80 
  protocol="HTTP"
  default_action { 
    type="forward" 
    target_group_arn = aws_lb_target_group.this.arn 
    }
}
output "alb_dns_name" { value = aws_lb.this.dns_name }
output "tg_arn"       { value = aws_lb_target_group.this.arn }
