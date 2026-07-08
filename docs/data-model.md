# Troglodyte Works Data Model

Everything in the platform has a unique ID.

-------------------------------------------------

Customer

customer_id
name
email
subscription
services[]

-------------------------------------------------

Service

service_id
customer_id
type
status
servers[]

-------------------------------------------------

Server

server_id
service_id
game
name
status
hostname
public_ip
ports
settings
mods
backups
logs

-------------------------------------------------

Game

game_id
name
version
maps[]
supported_mods[]

-------------------------------------------------

Map

map_id
game_id
name
display_name

-------------------------------------------------

Mod

mod_id
game_id
curseforge_id
name
version
status

-------------------------------------------------

Backup

backup_id
server_id
created
size
reason

-------------------------------------------------

Log

log_id
server_id
created
level
message

-------------------------------------------------

Tool

tool_id
name
mcp_server
permissions

-------------------------------------------------

Agent

agent_id
role
available_tools[]
