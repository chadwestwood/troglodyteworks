# TWE Database Schema

## Purpose

This document defines the core business entities and relationships for Troglodyte Works Experience.

It is the source of truth for future PostgreSQL migrations and application models.

## Core Relationships

- A user may belong to multiple communities.
- A user may own multiple communities.
- A community may have multiple users.
- A community may have multiple game servers.
- A game server may have multiple instances.
- An instance represents a playable space such as an ARK map or Minecraft world.

## Entities

### User

Represents a person with a TWE account.

Fields:

- id
- email
- password_hash
- display_name
- created_at
- updated_at

### Community

Represents a persistent social and organizational space.

Fields:

- id
- name
- slug
- description
- created_by
- created_at
- updated_at

### Community Membership

Connects a user to a community.

Fields:

- id
- user_id
- community_id
- role
- joined_at

Possible roles:

- owner
- admin
- moderator
- member

### Game Server

Represents a logical game environment belonging to a community.

Fields:

- id
- community_id
- name
- slug
- game_type
- management_adapter
- status
- created_at
- updated_at

### Game Instance

Represents a playable space managed under a game server.

Examples include:

- ARK map
- Minecraft world
- Palworld world
- other game-specific environments

Fields:

- id
- game_server_id
- name
- slug
- instance_type
- game_identifier
- status
- sort_order
- created_at
- updated_at

### Server Action

Represents a requested management action for a game instance.

Fields:

- id
- game_instance_id
- requested_by
- action_type
- status
- requested_at
- started_at
- completed_at
- result_message

## Initial Seed Data

### User

- display_name: Chad
- role: application administrator

### Community

- name: Cohorts in the Wild
- slug: cohorts-in-the-wild

### Membership

- user: Chad
- community: Cohorts in the Wild
- role: owner

### Game Server

- name: Cohorts in the Wild
- game_type: ARK Survival Ascended
- management_adapter: local_asa

### Game Instance

- name: Genesis
- instance_type: map
- game_identifier: Genesis_WP
