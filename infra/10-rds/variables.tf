variable "region" { type = string }
variable "name_prefix" { type = string }  # 例: "papyrus"
variable "db_username" { type = string }
variable "db_password" {
  type      = string
  sensitive = true
}
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "ecs_tasks_sg_id" { type = string }  # ECSタスク用SG（発信のみ想定）
