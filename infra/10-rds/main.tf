locals {
  tags = {
    Project = var.name_prefix
    Env     = "dev"
    Owner   = "self"
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-rds-subnet"
  subnet_ids = var.private_subnet_ids
  tags       = local.tags
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds-sg"
  description = "Ingress 5432 from ECS tasks SG only"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

resource "aws_vpc_security_group_ingress_rule" "from_tasks_5432" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = var.ecs_tasks_sg_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "ECS tasks -> RDS 5432"
}

resource "aws_db_parameter_group" "pg" {
  name   = "${var.name_prefix}-pg16-min"
  family = "postgres16"
  # 最小：今日は安全パラメータのみ。詳細は明日。
  parameter {
    name  = "log_min_duration_statement"
    value = "500" # ms
  }
  parameter {
    name  = "log_connections"
    value = "1"
  }
  tags = local.tags
}

resource "aws_db_instance" "this" {
  identifier                 = "${var.name_prefix}-pg16-dev"
  engine                     = "postgres"
  engine_version             = "16"
  instance_class             = "db.t4g.micro"
  allocated_storage          = 20
  db_name                    = "papyrus"
  username                   = var.db_username
  password                   = var.db_password
  db_subnet_group_name       = aws_db_subnet_group.this.name
  vpc_security_group_ids     = [aws_security_group.rds.id]
  parameter_group_name       = aws_db_parameter_group.pg.name

  storage_encrypted          = true
  publicly_accessible        = false
  multi_az                   = false
  backup_retention_period    = 1
  deletion_protection        = false
  skip_final_snapshot        = true

  apply_immediately          = true
  tags                       = local.tags
}
