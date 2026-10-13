# 数据库设计

## users
id UUID PK
email
password_hash / auth_provider
created_at
updated_at

## cases
id UUID PK
user_id FK
name
description
status
created_at
updated_at

## files
id UUID PK
case_id FK
original_filename
mime_type
size
sha256
storage_key
status
created_at
deleted_at

## document_analyses
id UUID PK
file_id FK
provider
model
prompt_version
raw_text
classification
structured_json JSONB
confidence
created_at

## evidence
id UUID PK
case_id FK
source_file_id FK
evidence_number
title
category
event_date
summary
proof_purpose
confidence
review_status
created_at
updated_at

## events
id UUID PK
case_id FK
event_date
event_time
title
description
confidence
review_status
created_at
updated_at

## evidence_events
evidence_id FK
event_id FK
PRIMARY KEY(evidence_id,event_id)

## persons
id UUID PK
case_id FK
name
role
organization
confidence
created_at

## evidence_persons
evidence_id FK
person_id FK

## claims
id UUID PK
case_id FK
title
description
created_at

## evidence_claims
evidence_id FK
claim_id FK

## review_items
id UUID PK
case_id FK
entity_type
entity_id
field_name
ai_value JSONB
user_value JSONB
status
created_at
updated_at

## export_jobs
id UUID PK
case_id FK
format
status
storage_key
error_message
created_at
completed_at

## audit_logs
id UUID PK
case_id FK
user_id FK
action
entity_type
entity_id
metadata JSONB
created_at

## 原则

删除采用 soft delete。
所有外键必须有索引。
JSONB 只用于 AI 原始结构化结果，不代替核心关系表。
