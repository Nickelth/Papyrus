provider "aws" {
  region = var.region
  # 認証はOIDCで実行するGitHub Actions用のロールを使う場合は
  # 環境変数のAWS_*に任せる。ローカル実行はプロファイルでも可。
}
