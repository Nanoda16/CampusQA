-- ============================================================
-- CampusQA 数据库初始化脚本
-- 河海大学校园知识问答助手
-- ============================================================

CREATE DATABASE IF NOT EXISTS campus_qa
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE campus_qa;

-- ============================================================
-- 1. 系统用户表
-- ============================================================
CREATE TABLE IF NOT EXISTS sys_user (
    id              BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    username        VARCHAR(50)     NOT NULL                 COMMENT '用户名',
    password_hash   VARCHAR(255)    NOT NULL                 COMMENT '密码哈希(BCrypt)',
    nickname        VARCHAR(50)     DEFAULT NULL             COMMENT '昵称',
    email           VARCHAR(100)    DEFAULT NULL             COMMENT '邮箱',
    role            VARCHAR(20)     DEFAULT 'student'        COMMENT '角色: student/teacher/admin',
    avatar          VARCHAR(255)    DEFAULT NULL             COMMENT '头像URL',
    status          TINYINT         DEFAULT 1                COMMENT '状态: 1=启用, 0=禁用/软删除',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_username (username),
    KEY idx_role (role),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统用户表';

-- ============================================================
-- 2. 知识库文档表
-- ============================================================
CREATE TABLE IF NOT EXISTS kb_document (
    id              BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    title           VARCHAR(255)    NOT NULL                 COMMENT '文档标题',
    content         LONGTEXT        DEFAULT NULL             COMMENT '文档内容',
    category        VARCHAR(50)     DEFAULT NULL             COMMENT '分类: news/academic/admin/departments等',
    department      VARCHAR(100)    DEFAULT NULL             COMMENT '所属部门',
    file_type       VARCHAR(20)     DEFAULT NULL             COMMENT '文件类型: pdf/docx/txt/md',
    file_path       VARCHAR(500)    DEFAULT NULL             COMMENT '文件存储路径',
    source_url      VARCHAR(500)    DEFAULT NULL             COMMENT '来源URL',
    tags            JSON            DEFAULT NULL             COMMENT '标签数组',
    chunk_count     INT             DEFAULT 0                COMMENT '切片数量',
    status          TINYINT         DEFAULT 1                COMMENT '文档处理状态: 1=UPLOADED,2=PROCESSING,3=READY,4=FAILED',
    created_by      BIGINT          DEFAULT NULL             COMMENT '上传用户ID',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_category (category),
    KEY idx_department (department),
    KEY idx_status (status),
    KEY idx_created_by (created_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库文档表';

-- ============================================================
-- 3. 问答记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS qa_record (
    id              BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    user_id         BIGINT          NOT NULL                 COMMENT '用户ID (FK → sys_user)',
    session_id      VARCHAR(100)    DEFAULT NULL             COMMENT '会话ID, 用于分组',
    question        TEXT            NOT NULL                 COMMENT '用户问题',
    answer          LONGTEXT        DEFAULT NULL             COMMENT 'AI回答',
    sources         JSON            DEFAULT NULL             COMMENT '引用的文档来源列表',
    tokens_used     INT             DEFAULT 0                COMMENT '消耗的token数',
    feedback        TINYINT         DEFAULT 0                COMMENT '反馈: 0=无, 1=有用, 2=无用',
    duration_ms     INT             DEFAULT NULL             COMMENT '响应耗时(毫秒)',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_user_id (user_id),
    KEY idx_session_id (session_id),
    KEY idx_created_at (created_at),
    CONSTRAINT fk_qa_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='问答记录表';

-- ============================================================
-- 4. 文档状态机迁移（新增字段，不破坏现有数据）
-- ============================================================
-- status 列已存在（TINYINT DEFAULT 1），含义变更为文档处理状态
-- chunk_count 列已存在，保持不动
--
-- 新增字段：
--   error_message  — 处理失败时的详细错误信息
--   processed_at   — 处理完成时间（READY/FAILED 时设置）
ALTER TABLE kb_document
    ADD COLUMN error_message VARCHAR(500) DEFAULT NULL COMMENT '处理失败时的错误信息' AFTER chunk_count,
    ADD COLUMN processed_at   DATETIME     DEFAULT NULL COMMENT '处理完成时间' AFTER error_message;
