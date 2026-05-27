-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)
--
-- Host: localhost    Database: rjfinshed
-- ------------------------------------------------------
-- Server version	8.0.45

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `audit_log`
--

DROP TABLE IF EXISTS `audit_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_log` (
  `timestamp` datetime DEFAULT NULL,
  `user` varchar(255) DEFAULT NULL,
  `ip` varchar(255) DEFAULT NULL,
  `action` varchar(255) DEFAULT NULL,
  `details` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_log`
--

LOCK TABLES `audit_log` WRITE;
/*!40000 ALTER TABLE `audit_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `audit_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `batches`
--

DROP TABLE IF EXISTS `batches`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `batches` (
  `batch_id` varchar(64) NOT NULL COMMENT 'BATCH-YYYYMM-NNN',
  `batch_no` int NOT NULL,
  `batch_code` varchar(16) DEFAULT NULL,
  `model_type` varchar(100) NOT NULL COMMENT 'Single model per batch',
  `major_category` varchar(32) DEFAULT NULL,
  `base_capacity` int DEFAULT NULL,
  `capacity_override` int DEFAULT NULL,
  `capacity` int NOT NULL COMMENT 'G/XS=30, AUTO=27',
  `status` varchar(32) NOT NULL DEFAULT 'Predicted' COMMENT 'Predicted / Confirmed / In_Production / Completed',
  `due_date_start` date DEFAULT NULL,
  `due_date_end` date DEFAULT NULL,
  `expected_inbound_date` date DEFAULT NULL,
  `capacity_snapshot` json DEFAULT NULL COMMENT 'Capacity ratio snapshot at generation',
  `source` varchar(32) NOT NULL DEFAULT 'algorithm' COMMENT 'algorithm / manual',
  `production_line_id` varchar(64) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_id`),
  KEY `idx_batches_status` (`status`),
  KEY `idx_batches_model` (`model_type`),
  KEY `idx_batches_line` (`production_line_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `batches`
--

LOCK TABLES `batches` WRITE;
/*!40000 ALTER TABLE `batches` DISABLE KEYS */;
/*!40000 ALTER TABLE `batches` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cloud_sync_outbox`
--

DROP TABLE IF EXISTS `cloud_sync_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cloud_sync_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` varchar(128) NOT NULL,
  `event_type` varchar(64) NOT NULL,
  `biz_key` varchar(128) NOT NULL DEFAULT '',
  `payload_json` longtext NOT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'pending',
  `retry_count` int NOT NULL DEFAULT '0',
  `last_error` text,
  `next_retry_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `synced_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cloud_sync_event_id` (`event_id`),
  KEY `idx_cloud_sync_status_retry` (`status`,`next_retry_at`,`id`),
  KEY `idx_cloud_sync_biz_key` (`biz_key`),
  KEY `idx_cloud_sync_event_type` (`event_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cloud_sync_outbox`
--

LOCK TABLES `cloud_sync_outbox` WRITE;
/*!40000 ALTER TABLE `cloud_sync_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `cloud_sync_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `contract_records`
--

DROP TABLE IF EXISTS `contract_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `contract_records` (
  `contract_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `customer` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `file_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `file_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `file_hash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `uploader` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `upload_time` datetime DEFAULT NULL,
  KEY `idx_contract_id` (`contract_id`),
  KEY `idx_contract_upload_time` (`upload_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `contract_records`
--

LOCK TABLES `contract_records` WRITE;
/*!40000 ALTER TABLE `contract_records` DISABLE KEYS */;
/*!40000 ALTER TABLE `contract_records` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `dealer_applications`
--

DROP TABLE IF EXISTS `dealer_applications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dealer_applications` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `dealer_code` varchar(128) NOT NULL,
  `company_name` varchar(255) NOT NULL,
  `phone` varchar(64) NOT NULL,
  `contact_name` varchar(128) NOT NULL,
  `region` varchar(255) DEFAULT '',
  `role` varchar(32) NOT NULL DEFAULT 'dealer',
  `regional_manager_name` varchar(128) DEFAULT '',
  `remark` text,
  `status` varchar(32) NOT NULL DEFAULT 'pending',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `dealer_code` (`dealer_code`),
  UNIQUE KEY `phone` (`phone`),
  KEY `idx_status` (`status`),
  KEY `idx_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dealer_applications`
--

LOCK TABLES `dealer_applications` WRITE;
/*!40000 ALTER TABLE `dealer_applications` DISABLE KEYS */;
/*!40000 ALTER TABLE `dealer_applications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `dealer_order_sync_events`
--

DROP TABLE IF EXISTS `dealer_order_sync_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dealer_order_sync_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` varchar(64) NOT NULL,
  `order_no` varchar(64) NOT NULL,
  `event_type` varchar(64) NOT NULL,
  `source` varchar(32) NOT NULL DEFAULT 'wechat',
  `payload_json` json NOT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'pending',
  `attempts` int NOT NULL DEFAULT '0',
  `last_error` text,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `acked_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `event_id` (`event_id`),
  KEY `idx_sync_events_order` (`order_no`),
  KEY `idx_sync_events_status` (`status`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dealer_order_sync_events`
--

LOCK TABLES `dealer_order_sync_events` WRITE;
/*!40000 ALTER TABLE `dealer_order_sync_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `dealer_order_sync_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `dealer_orders`
--

DROP TABLE IF EXISTS `dealer_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dealer_orders` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `order_no` varchar(64) NOT NULL,
  `line_no` int NOT NULL DEFAULT '1',
  `dealer_id` varchar(128) NOT NULL,
  `dealer_name` varchar(255) NOT NULL,
  `dealer_phone` varchar(64) DEFAULT '',
  `regional_manager_name` varchar(128) DEFAULT '',
  `customer_name` varchar(255) NOT NULL,
  `contact_name` varchar(128) NOT NULL,
  `contact_phone` varchar(64) NOT NULL,
  `model` varchar(255) NOT NULL,
  `batch_no` varchar(255) DEFAULT '',
  `eta` varchar(64) DEFAULT '',
  `inventory_type` varchar(32) DEFAULT '',
  `quantity` int NOT NULL DEFAULT '1',
  `approved_qty` int NOT NULL DEFAULT '0',
  `allocated_qty` int NOT NULL DEFAULT '0',
  `delivery_date` varchar(64) DEFAULT '',
  `remark` text,
  `status` varchar(32) NOT NULL DEFAULT 'pending',
  `regional_review_status` varchar(32) NOT NULL DEFAULT 'pending',
  `regional_review_note` text,
  `regional_reviewed_by` varchar(128) DEFAULT '',
  `regional_reviewed_at` datetime DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `reviewed_by` varchar(128) DEFAULT '',
  `contract_no` varchar(128) DEFAULT '',
  `v7_order_no` varchar(128) DEFAULT '',
  `review_note` text,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `extra_remark` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
  `ERMQ` int NOT NULL,
  `factory_pending` tinyint(1) NOT NULL,
  `source` varchar(32) NOT NULL DEFAULT 'wechat',
  `last_synced_at` datetime DEFAULT NULL,
  `sync_status` varchar(32) NOT NULL DEFAULT 'pending',
  `sync_error` text,
  `factory_reviewed_at` datetime DEFAULT NULL,
  `factory_reviewed_by` varchar(128) DEFAULT '',
  `extra_remark_reviewed_at` datetime DEFAULT NULL,
  `extra_remark_reviewed_by` varchar(128) DEFAULT '',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dealer_order_line` (`order_no`,`line_no`),
  KEY `idx_dealer_order_no` (`order_no`),
  KEY `idx_dealer_id` (`dealer_id`),
  KEY `idx_status` (`status`),
  KEY `idx_batch_model_status` (`batch_no`,`model`,`status`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dealer_orders`
--

LOCK TABLES `dealer_orders` WRITE;
/*!40000 ALTER TABLE `dealer_orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `dealer_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `factory_plan`
--

DROP TABLE IF EXISTS `factory_plan`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `factory_plan` (
  `id` int NOT NULL AUTO_INCREMENT,
  `合同号` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `机型` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `排产数量` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `要求交期` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `状态` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `备注` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `订单号` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `客户名` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `代理商` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `指定批次/来源` json DEFAULT NULL,
  `temp_date` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_fp_contract_status_due` (`合同号`,`状态`,`要求交期`) USING BTREE,
  KEY `idx_fp_due_date` (`要求交期`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `factory_plan`
--

LOCK TABLES `factory_plan` WRITE;
/*!40000 ALTER TABLE `factory_plan` DISABLE KEYS */;
/*!40000 ALTER TABLE `factory_plan` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `finished_goods_data`
--

DROP TABLE IF EXISTS `finished_goods_data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finished_goods_data` (
  `批次号` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `机型` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `流水号` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `状态` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `更新时间` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `占用订单号` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `客户` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `代理商` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `合同备注` text COLLATE utf8mb4_general_ci,
  `合同号` varchar(100) COLLATE utf8mb4_general_ci DEFAULT '',
  `订单备注` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `预计入库时间` datetime DEFAULT NULL,
  `机台备注/配置` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `Location_Code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  KEY `idx_fg_status_model_order` (`状态`,`机型`,`占用订单号`) USING BTREE,
  KEY `idx_fg_batch_status` (`批次号`,`状态`) USING BTREE,
  KEY `idx_fg_updated_at` (`更新时间`) USING BTREE,
  KEY `idx_fg_status_model` (`状态`,`机型`) USING BTREE,
  KEY `idx_fg_status_location` (`状态`,`Location_Code`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finished_goods_data`
--

LOCK TABLES `finished_goods_data` WRITE;
/*!40000 ALTER TABLE `finished_goods_data` DISABLE KEYS */;
/*!40000 ALTER TABLE `finished_goods_data` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trg_fg_wechat_summary_ai` AFTER INSERT ON `finished_goods_data` FOR EACH ROW BEGIN
  CALL `refresh_wechat_batch_summary_group`(NEW.`批次号`, NEW.`预计入库时间`, NEW.`机型`);
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trg_fg_wechat_summary_au` AFTER UPDATE ON `finished_goods_data` FOR EACH ROW BEGIN
  CALL `refresh_wechat_batch_summary_group`(OLD.`批次号`, OLD.`预计入库时间`, OLD.`机型`);
  IF NOT (
    OLD.`批次号` <=> NEW.`批次号`
    AND OLD.`预计入库时间` <=> NEW.`预计入库时间`
    AND OLD.`机型` <=> NEW.`机型`
  ) THEN
    CALL `refresh_wechat_batch_summary_group`(NEW.`批次号`, NEW.`预计入库时间`, NEW.`机型`);
  END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trg_fg_wechat_summary_ad` AFTER DELETE ON `finished_goods_data` FOR EACH ROW BEGIN
  CALL `refresh_wechat_batch_summary_group`(OLD.`批次号`, OLD.`预计入库时间`, OLD.`机型`);
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `forecast_batch_slots`
--

DROP TABLE IF EXISTS `forecast_batch_slots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `forecast_batch_slots` (
  `slot_no` int NOT NULL,
  `model_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `capacity` int NOT NULL,
  `batch_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `source` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'ratio',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`slot_no`),
  KEY `idx_forecast_batch_slots_model` (`model_type`),
  KEY `idx_forecast_batch_slots_batch` (`batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `forecast_batch_slots`
--

LOCK TABLES `forecast_batch_slots` WRITE;
/*!40000 ALTER TABLE `forecast_batch_slots` DISABLE KEYS */;
/*!40000 ALTER TABLE `forecast_batch_slots` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `import_staging`
--

DROP TABLE IF EXISTS `import_staging`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `import_staging` (
  `流水号` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `批次号` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `机型` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `状态` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '待入库',
  `预计入库时间` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `机台备注/配置` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
  PRIMARY KEY (`流水号`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `import_staging`
--

LOCK TABLES `import_staging` WRITE;
/*!40000 ALTER TABLE `import_staging` DISABLE KEYS */;
/*!40000 ALTER TABLE `import_staging` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `model_dictionary`
--

DROP TABLE IF EXISTS `model_dictionary`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `model_dictionary` (
  `id` int NOT NULL AUTO_INCREMENT,
  `model_name` varchar(100) NOT NULL,
  `model_family` varchar(100) DEFAULT '',
  `model_size` varchar(100) DEFAULT NULL,
  `sort_order` int NOT NULL DEFAULT '0',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `remark` varchar(255) DEFAULT '',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_model_dictionary_name` (`model_name`)
) ENGINE=InnoDB AUTO_INCREMENT=293 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `model_dictionary`
--

LOCK TABLES `model_dictionary` WRITE;
/*!40000 ALTER TABLE `model_dictionary` DISABLE KEYS */;
INSERT INTO `model_dictionary` VALUES (243,'FR-400G','中小型G',NULL,1,1,'','2026-05-13 20:34:19'),(244,'FR-500G','中小型G',NULL,4,1,'','2026-05-13 20:34:19'),(245,'FR-600G','中小型G',NULL,7,1,'','2026-05-13 20:34:19'),(246,'FR-400XS(PRO)','中小型XS',NULL,2,1,'','2026-05-13 20:34:19'),(247,'FR-500XS(PRO)','中小型XS',NULL,5,1,'','2026-05-13 20:34:19'),(248,'FR-600XS(PRO)','中小型XS',NULL,8,1,'','2026-05-13 20:34:19'),(249,'FR-7055XS(PRO)','中大型XS',NULL,11,1,'','2026-05-13 20:34:19'),(250,'FR-8055XS(PRO)','中大型XS',NULL,12,1,'','2026-05-13 20:34:19'),(251,'FR-8060XS(PRO)','中大型XS',NULL,14,1,'','2026-05-13 20:34:19'),(254,'FR-500AUTO','中小型AUTO',NULL,6,1,'','2026-05-13 20:34:19'),(255,'FR-600AUTO','中小型AUTO',NULL,9,1,'','2026-05-13 20:34:19'),(256,'FR-7055AUTO','中大型AUTO',NULL,10,1,'','2026-05-13 20:34:19'),(257,'FR-8055AUTO','中大型AUTO',NULL,13,1,'','2026-05-13 20:34:19'),(258,'FR-1100XS(PRO)','特殊',NULL,15,1,'','2026-05-09 00:49:01'),(259,'FL-1390XS(PRO)','特殊',NULL,16,1,'','2026-05-09 00:49:01'),(260,'FL-1610XS','特殊',NULL,17,1,'','2026-05-09 00:49:01'),(261,'FR-1080Y','特殊',NULL,18,1,'','2026-05-09 00:49:01'),(262,'FR-850MS','特殊',NULL,21,1,'','2026-05-09 00:49:01'),(264,'FT','特殊',NULL,22,1,'','2026-05-09 00:49:01'),(265,'FR-1080XS(PRO)','特殊',NULL,23,1,'','2026-05-09 00:49:01'),(266,'FR-8060AUTO','中大型AUTO',NULL,24,1,'','2026-05-13 20:34:19'),(268,'FR-8560XS(PRO)','特殊',NULL,19,1,'','2026-05-09 00:49:01'),(269,'FR-8060Y(PRO)','特殊',NULL,20,1,'','2026-05-09 00:49:01'),(291,'FH-300C','中小型G',NULL,0,1,'','2026-05-13 20:34:19'),(292,'FR-400AUTO','中小型AUTO',NULL,3,1,'','2026-05-13 20:34:19');
/*!40000 ALTER TABLE `model_dictionary` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `operation_log`
--

DROP TABLE IF EXISTS `operation_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `operation_log` (
  `log_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `actor` longtext COLLATE utf8mb4_general_ci,
  `action` longtext COLLATE utf8mb4_general_ci,
  `target_type` longtext COLLATE utf8mb4_general_ci,
  `target_id` longtext COLLATE utf8mb4_general_ci,
  `detail` json DEFAULT NULL,
  `created_at` datetime(3) DEFAULT NULL,
  PRIMARY KEY (`log_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `operation_log`
--

LOCK TABLES `operation_log` WRITE;
/*!40000 ALTER TABLE `operation_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `operation_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `plan_import`
--

DROP TABLE IF EXISTS `plan_import`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `plan_import` (
  `批次号` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `机型` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `流水号` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `预计入库时间` datetime DEFAULT NULL,
  `客户` varchar(200) COLLATE utf8mb4_general_ci DEFAULT '',
  `代理商` varchar(200) COLLATE utf8mb4_general_ci DEFAULT '',
  `合同备注` text COLLATE utf8mb4_general_ci,
  `合同号` varchar(100) COLLATE utf8mb4_general_ci DEFAULT '',
  `订单号` varchar(100) COLLATE utf8mb4_general_ci DEFAULT '',
  `f4` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `状态` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '待入库',
  KEY `idx_import_batch_model` (`批次号`,`机型`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `plan_import`
--

LOCK TABLES `plan_import` WRITE;
/*!40000 ALTER TABLE `plan_import` DISABLE KEYS */;
/*!40000 ALTER TABLE `plan_import` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `planning_records`
--

DROP TABLE IF EXISTS `planning_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `planning_records` (
  `order_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `model` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `plan_info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `planning_records`
--

LOCK TABLES `planning_records` WRITE;
/*!40000 ALTER TABLE `planning_records` DISABLE KEYS */;
/*!40000 ALTER TABLE `planning_records` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `production_lines`
--

DROP TABLE IF EXISTS `production_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `production_lines` (
  `line_id` varchar(64) NOT NULL,
  `line_name` varchar(100) NOT NULL,
  `current_batch_id` varchar(64) DEFAULT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'Idle' COMMENT 'Idle / Busy / Maintenance',
  `display_order` int NOT NULL DEFAULT '0',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`line_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `production_lines`
--

LOCK TABLES `production_lines` WRITE;
/*!40000 ALTER TABLE `production_lines` DISABLE KEYS */;
INSERT INTO `production_lines` VALUES ('line-01','产线 1',NULL,'Idle',1,'2026-05-23 14:49:03'),('line-02','产线 2',NULL,'Idle',2,'2026-05-23 14:49:03'),('line-03','产线 3',NULL,'Idle',3,'2026-05-23 14:49:03'),('line-04','产线 4',NULL,'Idle',4,'2026-05-23 14:49:03'),('line-05','产线 5',NULL,'Idle',5,'2026-05-23 14:49:03'),('line-06','产线 6',NULL,'Idle',6,'2026-05-23 14:49:03'),('line-07','产线 7',NULL,'Idle',7,'2026-05-23 14:49:03'),('line-08','产线 8',NULL,'Idle',8,'2026-05-23 14:49:03'),('line-09','产线 9',NULL,'Idle',9,'2026-05-23 14:49:03'),('line-10','产线 10',NULL,'Idle',10,'2026-05-23 14:49:03'),('line-11','产线 11',NULL,'Idle',11,'2026-05-23 14:49:03'),('line-12','产线 12',NULL,'Idle',12,'2026-05-23 14:49:03'),('line-13','产线 13',NULL,'Idle',13,'2026-05-23 14:49:03'),('line-14','产线 14',NULL,'Idle',14,'2026-05-23 14:49:03'),('line-15','产线 15',NULL,'Idle',15,'2026-05-23 14:49:03'),('line-16','产线 16',NULL,'Idle',16,'2026-05-23 14:49:03'),('line-17','产线 17',NULL,'Idle',17,'2026-05-23 14:49:03'),('line-18','产线 18',NULL,'Idle',18,'2026-05-23 14:49:03'),('line-19','产线 19',NULL,'Idle',19,'2026-05-23 14:49:03'),('line-20','产线 20',NULL,'Idle',20,'2026-05-23 14:49:03');
/*!40000 ALTER TABLE `production_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `production_queue`
--

DROP TABLE IF EXISTS `production_queue`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `production_queue` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `model_type` varchar(100) NOT NULL,
  `contract_no` varchar(255) NOT NULL,
  `customer` varchar(255) DEFAULT NULL,
  `dealer` varchar(255) DEFAULT NULL,
  `due_date` date NOT NULL,
  `quantity_remaining` int NOT NULL COMMENT 'Remaining units not yet batched',
  `status` varchar(32) DEFAULT 'Waiting' COMMENT 'Waiting / Pulled',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_queue_model_due` (`model_type`,`due_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `production_queue`
--

LOCK TABLES `production_queue` WRITE;
/*!40000 ALTER TABLE `production_queue` DISABLE KEYS */;
/*!40000 ALTER TABLE `production_queue` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_permissions` (
  `role_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `func_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `create_time` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  UNIQUE KEY `uq_role_permissions_role_func` (`role_id`,`func_code`) USING BTREE,
  CONSTRAINT `fk_role_permissions_role` FOREIGN KEY (`role_id`) REFERENCES `roles` (`role_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_permissions`
--

LOCK TABLES `role_permissions` WRITE;
/*!40000 ALTER TABLE `role_permissions` DISABLE KEYS */;
INSERT INTO `role_permissions` VALUES ('Prod','INBOUND','2026/2/27 10:00'),('Prod','SHIP_CONFIRM','2026/2/27 10:00'),('Prod','MACHINE_EDIT','2026/2/27 10:00'),('Prod','ARCHIVE','2026/2/27 10:00'),('Prod','QUERY','2026/2/27 10:00'),('Prod','MACHINE_EDIT_MODEL',NULL),('Prod','WAREHOUSE_MAP',NULL),('Inbound','INBOUND',NULL),('Inbound','WAREHOUSE_MAP',NULL),('Sales','CONTRACT',NULL),('Sales','SALES_CREATE',NULL),('Sales','SALES_ALLOC',NULL),('Sales','INBOUND',NULL),('Sales','QUERY',NULL),('Sales','WAREHOUSE_MAP',NULL),('Boss','ARCHIVE',NULL),('Boss','CONTRACT',NULL),('Boss','QUERY',NULL),('Boss','WAREHOUSE_MAP',NULL),('Boss','LOG_VIEW',NULL),('fileediter','ARCHIVE',NULL),('fileediter','WAREHOUSE_MAP',NULL),('fileediter','LOG_VIEW',NULL),('Boss','SANDBOX_VIEW',NULL),('Boss','SANDBOX_EDIT',NULL),('Boss','MODEL_DICTIONARY',NULL),('Boss','SALES_CREATE',NULL),('Boss','SALES_ALLOC',NULL),('Boss','SHIP_CONFIRM',NULL),('Boss','MACHINE_EDIT',NULL),('Boss','INBOUND',NULL),('Boss','TRACEABILITY',NULL),('Sales','LOG_VIEW',NULL),('Sales','TRACEABILITY',NULL),('Prod','LOG_VIEW',NULL),('Boss','KANBAN_VIEW',NULL),('Admin','ARCHIVE',NULL),('Admin','CONTRACT',NULL),('Admin','INBOUND',NULL),('Admin','KANBAN_VIEW',NULL),('Admin','LOG_VIEW',NULL),('Admin','MACHINE_EDIT',NULL),('Admin','MODEL_DICTIONARY',NULL),('Admin','QUERY',NULL),('Admin','SALES_ALLOC',NULL),('Admin','SALES_CREATE',NULL),('Admin','SANDBOX_VIEW',NULL),('Admin','SHIP_CONFIRM',NULL),('Admin','TRACEABILITY',NULL),('Admin','USER_MANAGE',NULL),('Admin','WAREHOUSE_MAP',NULL),('Admin','SANDBOX_EDIT',NULL),('LineOperator','MOBILE_KANBAN_ASSIGN',NULL),('LineOperator','MOBILE_KANBAN_VIEW',NULL),('Admin','DEALER_ORDER_REVIEW',NULL),('Boss','DEALER_ORDER_REVIEW',NULL),('Sales','DEALER_ORDER_REVIEW',NULL);
/*!40000 ALTER TABLE `role_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `role_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `role_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  PRIMARY KEY (`role_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES ('Admin','Admin'),('Boss','Boss'),('fileediter','档案员'),('Inbound','Inbound'),('LineOperator','产线操作员'),('Prod','Prod'),('Sales','Sales');
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `rush_order_queue`
--

DROP TABLE IF EXISTS `rush_order_queue`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `rush_order_queue` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `contract_no` varchar(100) NOT NULL,
  `customer` varchar(200) DEFAULT '',
  `dealer_name` varchar(200) DEFAULT '',
  `model_type` varchar(100) NOT NULL,
  `due_date` date DEFAULT NULL,
  `remark` text,
  `source` varchar(50) NOT NULL DEFAULT 'contract',
  `status` varchar(30) NOT NULL DEFAULT 'pending',
  `created_by` varchar(100) DEFAULT '',
  `updated_by` varchar(100) DEFAULT '',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rush_order_queue_status` (`status`,`created_at`),
  KEY `idx_rush_order_queue_contract` (`contract_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rush_order_queue`
--

LOCK TABLES `rush_order_queue` WRITE;
/*!40000 ALTER TABLE `rush_order_queue` DISABLE KEYS */;
/*!40000 ALTER TABLE `rush_order_queue` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sales_orders`
--

DROP TABLE IF EXISTS `sales_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sales_orders` (
  `订单号` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `客户名` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `代理商` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `需求机型` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `需求数量` int DEFAULT '0',
  `下单时间` datetime DEFAULT NULL,
  `备注` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `包装选项` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `发货时间` datetime DEFAULT NULL,
  `指定批次/来源` json DEFAULT NULL,
  `status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `delete_reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  KEY `idx_orders_status_time` (`status`,`下单时间`) USING BTREE,
  KEY `idx_orders_delivery` (`发货时间`) USING BTREE,
  KEY `idx_orders_customer` (`客户名`) USING BTREE,
  KEY `idx_orders_customer_time` (`客户名`,`下单时间`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sales_orders`
--

LOCK TABLES `sales_orders` WRITE;
/*!40000 ALTER TABLE `sales_orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `sales_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `schema_version`
--

DROP TABLE IF EXISTS `schema_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `schema_version` (
  `version` int NOT NULL,
  `applied_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `schema_version`
--

LOCK TABLES `schema_version` WRITE;
/*!40000 ALTER TABLE `schema_version` DISABLE KEYS */;
INSERT INTO `schema_version` VALUES (1,'2026-05-07 05:35:34','Initial schema creation'),(2,'2026-05-07 05:35:34','plan_import: replace 机台备注/配置 with 客户, 代理商, 合同备注'),(3,'2026-05-07 07:33:54','add contract_no traceability columns'),(4,'2026-05-07 07:56:42','add persistent rush order queue'),(5,'2026-05-07 09:19:53','unify machine/order notes into contract remarks'),(6,'2026-05-08 04:08:58','normalize factory_plan status to 待规划'),(7,'2026-05-08 07:00:29','add remark column for rush order queue'),(8,'2026-05-08 10:01:26','normalize planned contracts linked to orders'),(9,'2026-05-18 11:15:39','add dealer_orders and wechat_batch_summary tables');
/*!40000 ALTER TABLE `schema_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `shipping_history`
--

DROP TABLE IF EXISTS `shipping_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `shipping_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `批次号` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `机型` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `流水号` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `状态` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `预计入库时间` datetime DEFAULT NULL,
  `更新时间` datetime DEFAULT NULL,
  `占用订单号` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `客户` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `代理商` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  `合同备注` text,
  `合同号` varchar(100) DEFAULT '',
  `archive_month` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT '',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_ship_month_time` (`archive_month`,`更新时间`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `shipping_history`
--

LOCK TABLES `shipping_history` WRITE;
/*!40000 ALTER TABLE `shipping_history` DISABLE KEYS */;
/*!40000 ALTER TABLE `shipping_history` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sys_operation_log`
--

DROP TABLE IF EXISTS `sys_operation_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_operation_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  `username` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  `operate_time` datetime DEFAULT NULL,
  `module` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  `action_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  `biz_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `serial_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  `order_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  `contract_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_sys_operation_log_time` (`operate_time`) USING BTREE,
  KEY `idx_sys_operation_log_user` (`user_id`,`operate_time`) USING BTREE,
  KEY `idx_sys_operation_log_module` (`module`,`action_type`,`biz_type`) USING BTREE,
  KEY `idx_sys_operation_log_sn` (`serial_no`) USING BTREE,
  KEY `idx_sys_operation_log_order` (`order_no`) USING BTREE,
  KEY `idx_sys_operation_log_contract` (`contract_no`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_operation_log`
--

LOCK TABLES `sys_operation_log` WRITE;
/*!40000 ALTER TABLE `sys_operation_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `sys_operation_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `system_config`
--

DROP TABLE IF EXISTS `system_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `system_config` (
  `config_key` varchar(100) NOT NULL,
  `config_value` text,
  `description` varchar(255) DEFAULT NULL,
  `updated_by` varchar(100) DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `system_config`
--

LOCK TABLES `system_config` WRITE;
/*!40000 ALTER TABLE `system_config` DISABLE KEYS */;
INSERT INTO `system_config` VALUES ('batch_break_days','30','Gap threshold in days','system','2026-04-28 12:24:58'),('capacity_ratio','{\"level2\": {\"G\": {\"中小型G\": 100}, \"XS\": {\"中大型XS\": 40, \"中小型XS\": 60}, \"AUTO\": {\"中大型AUTO\": 33, \"中小型AUTO\": 67}, \"SPECIAL\": {\"特殊\": 0}}, \"level3\": {\"特殊\": {\"特殊\": 0}, \"中小型G\": {\"FH-300C\": 25, \"FR-400G\": 50, \"FR-500G\": 5, \"FR-600G\": 20}, \"中大型XS\": {\"FR-7055XS(PRO)\": 50, \"FR-8055XS(PRO)\": 25, \"FR-8060XS(PRO)\": 25}, \"中小型XS\": {\"FR-400XS(PRO)\": 34, \"FR-500XS(PRO)\": 33, \"FR-600XS(PRO)\": 33}, \"中大型AUTO\": {\"FR-7055AUTO\": 38, \"FR-8055AUTO\": 37, \"FR-8060AUTO\": 25}, \"中小型AUTO\": {\"FR-400AUTO\": 34, \"FR-500AUTO\": 33, \"FR-600AUTO\": 33}}, \"level2_global\": {\"特殊\": 0, \"中小型G\": 20, \"中大型XS\": 20, \"中小型XS\": 30, \"中大型AUTO\": 10, \"中小型AUTO\": 20}}','两级产能比例配置','admin','2026-05-14 15:58:01'),('max_batch_slots','20','Max predicted/confirmed batches','system','2026-04-28 12:24:58'),('mes_webhook_secret','CHANGE_ME','MES webhook HMAC secret','system','2026-04-28 12:24:58'),('model_capacity','{\"G\":30,\"XS\":30,\"AUTO\":27}','Per-batch capacity per model','system','2026-04-28 12:24:58');
/*!40000 ALTER TABLE `system_config` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `transaction_log`
--

DROP TABLE IF EXISTS `transaction_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `transaction_log` (
  `时间` datetime DEFAULT NULL,
  `操作类型` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `流水号` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `操作员` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  KEY `idx_log_time` (`时间`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transaction_log`
--

LOCK TABLES `transaction_log` WRITE;
/*!40000 ALTER TABLE `transaction_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `transaction_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `units`
--

DROP TABLE IF EXISTS `units`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `units` (
  `unit_id` varchar(64) NOT NULL,
  `serial_no` varchar(100) DEFAULT NULL COMMENT 'Serial from finished_goods_data',
  `forecast_serial_no` varchar(64) DEFAULT NULL,
  `batch_id` varchar(64) NOT NULL,
  `slot_index` int NOT NULL COMMENT '1~30 position within batch',
  `model_type` varchar(100) NOT NULL COMMENT 'Must match batch.model_type',
  `production_line_id` varchar(64) DEFAULT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'Pending' COMMENT 'Pending / In_Production / In_Warehouse / Spot_Inventory / Sold',
  `contract_no` varchar(100) DEFAULT NULL,
  `customer` varchar(255) DEFAULT NULL,
  `dealer_id` varchar(64) DEFAULT NULL,
  `dealer_name` varchar(255) DEFAULT NULL,
  `due_date` date DEFAULT NULL,
  `sales_id` varchar(64) DEFAULT NULL,
  `order_remark` varchar(500) DEFAULT NULL,
  `is_locked` tinyint(1) NOT NULL DEFAULT '0',
  `locked_by` varchar(100) DEFAULT NULL,
  `locked_at` datetime DEFAULT NULL,
  `is_contract_pinned` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`unit_id`),
  UNIQUE KEY `uq_units_batch_slot` (`batch_id`,`slot_index`),
  KEY `idx_units_batch` (`batch_id`),
  KEY `idx_units_line_status` (`production_line_id`,`status`),
  KEY `idx_units_locked` (`is_locked`),
  KEY `idx_units_empty_container` (`status`,`contract_no`,`model_type`,`is_locked`),
  CONSTRAINT `fk_units_batch` FOREIGN KEY (`batch_id`) REFERENCES `batches` (`batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `units`
--

LOCK TABLES `units` WRITE;
/*!40000 ALTER TABLE `units` DISABLE KEYS */;
/*!40000 ALTER TABLE `units` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_sessions`
--

DROP TABLE IF EXISTS `user_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `token_hash` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `expires_at` datetime NOT NULL,
  `revoked` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` datetime DEFAULT NULL,
  `revoked_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uq_user_sessions_token_hash` (`token_hash`) USING BTREE,
  KEY `idx_user_sessions_username` (`username`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_sessions`
--

LOCK TABLES `user_sessions` WRITE;
/*!40000 ALTER TABLE `user_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `role` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `region` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'guangdong / non_guangdong',
  `wechat_openid` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'WeChat mini-program login',
  `status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `register_time` datetime DEFAULT NULL,
  `audit_time` datetime DEFAULT NULL,
  `auditor` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`username`) USING BTREE,
  KEY `fk_users_role` (`role`),
  KEY `idx_users_region` (`region`),
  KEY `idx_users_openid` (`wechat_openid`),
  CONSTRAINT `fk_users_role` FOREIGN KEY (`role`) REFERENCES `roles` (`role_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES ('011','831214','Sales','杨琴',NULL,NULL,'active','2026-02-28 10:06:00','2026-02-28 10:18:00','系统管理员'),('015','abc112233','Sales','朱裕玲',NULL,NULL,'active','2026-02-28 10:14:00','2026-02-28 10:18:00','系统管理员'),('admin','888','Admin','系统管理员',NULL,NULL,'active','2026-04-10 08:52:19','2026-04-10 08:52:19','System'),('b02','222','Inbound','222',NULL,NULL,'active','2026-04-01 09:00:48','2026-04-01 09:01:00','系统管理员'),('boss','888','Boss','老板',NULL,NULL,'active','2026-04-10 08:52:19','2026-04-10 09:36:07','系统管理员'),('fakeu','123','Inbound','驻车',NULL,NULL,'active','2026-03-31 15:40:14','2026-03-31 15:40:23','系统管理员'),('hmh','123456','Prod','胡旻辉',NULL,NULL,'active','2026-02-27 16:40:00','2026-02-27 16:43:00','系统管理员'),('inbound','123','Inbound','入库员',NULL,NULL,'active','2026-04-10 08:52:19','2026-04-10 08:52:19','System'),('kd','888','Prod','王致旻',NULL,NULL,'active','2026-02-27 15:27:00','2026-02-27 15:27:00','系统管理员'),('lihaoyu','123','Prod','李皓宇',NULL,NULL,'active','2026-02-27 09:48:00','2026-02-27 09:48:00','系统管理员'),('paizhao','123','fileediter','臭拍照的',NULL,NULL,'active','2026-04-24 15:58:08','2026-04-24 15:58:14','系统管理员'),('prod','123','Prod','仓管/生产',NULL,NULL,'active','2026-04-10 08:52:19','2026-04-10 08:52:19','System'),('rukuyuan','123','Inbound','admin',NULL,NULL,'active','2026-04-01 08:32:36','2026-04-01 08:33:04','系统管理员'),('sales','123','Sales','销售员',NULL,NULL,'active','2026-04-10 08:52:19','2026-04-10 08:52:19','System'),('test','123','LineOperator','cc',NULL,NULL,'active','2026-05-15 11:21:43','2026-05-15 11:21:53','系统管理员'),('test123','123','Inbound','fakeU',NULL,NULL,'active','2026-03-31 14:38:32','2026-03-31 14:38:46','系统管理员'),('xiaozhu','123456','Sales','朱孝二',NULL,NULL,'active','2026-03-07 09:34:08','2026-03-07 09:34:16','系统管理员'),('zc123','030705','Prod','1t4',NULL,NULL,'active','2026-04-10 10:45:02','2026-04-24 14:21:06','系统管理员'),('zhuxiaoyi','123456','Prod','朱孝一',NULL,NULL,'active','2026-02-27 09:45:00','2026-02-27 09:45:00','系统管理员');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `warehouse_layout`
--

DROP TABLE IF EXISTS `warehouse_layout`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `warehouse_layout` (
  `layout_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `layout_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
  `update_time` datetime DEFAULT NULL,
  PRIMARY KEY (`layout_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `warehouse_layout`
--

LOCK TABLES `warehouse_layout` WRITE;
/*!40000 ALTER TABLE `warehouse_layout` DISABLE KEYS */;
INSERT INTO `warehouse_layout` VALUES ('default','{\"slots\": [{\"id\": \"slot-1\", \"code\": \"A01\", \"x\": 20, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-2\", \"code\": \"A02\", \"x\": 360, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-3\", \"code\": \"A03\", \"x\": 740, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-4\", \"code\": \"A04\", \"x\": 1080, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-5\", \"code\": \"A05\", \"x\": 1460, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-6\", \"code\": \"A06\", \"x\": 1800, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-7\", \"code\": \"A07\", \"x\": 2180, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-8\", \"code\": \"A08\", \"x\": 2520, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-9\", \"code\": \"A09\", \"x\": 2900, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-10\", \"code\": \"A10\", \"x\": 3240, \"y\": 20, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-11\", \"code\": \"B01\", \"x\": 20, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-12\", \"code\": \"B02\", \"x\": 360, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-13\", \"code\": \"B03\", \"x\": 740, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-14\", \"code\": \"B04\", \"x\": 1080, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-15\", \"code\": \"B05\", \"x\": 1460, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-16\", \"code\": \"B06\", \"x\": 1800, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-17\", \"code\": \"B07\", \"x\": 2180, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-18\", \"code\": \"B08\", \"x\": 2520, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-19\", \"code\": \"B09\", \"x\": 2900, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-20\", \"code\": \"B10\", \"x\": 3240, \"y\": 200, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-21\", \"code\": \"C01\", \"x\": 20, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-22\", \"code\": \"C02\", \"x\": 360, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-23\", \"code\": \"C03\", \"x\": 740, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-24\", \"code\": \"C04\", \"x\": 1080, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-25\", \"code\": \"C05\", \"x\": 1460, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-26\", \"code\": \"C06\", \"x\": 1800, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-27\", \"code\": \"C07\", \"x\": 2180, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-28\", \"code\": \"C08\", \"x\": 2520, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-29\", \"code\": \"C09\", \"x\": 2900, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-30\", \"code\": \"C10\", \"x\": 3240, \"y\": 380, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-31\", \"code\": \"D01\", \"x\": 20, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-32\", \"code\": \"D02\", \"x\": 360, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-33\", \"code\": \"D03\", \"x\": 740, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-34\", \"code\": \"D04\", \"x\": 1080, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-35\", \"code\": \"D05\", \"x\": 1460, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-36\", \"code\": \"D06\", \"x\": 1800, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-37\", \"code\": \"D07\", \"x\": 2180, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-38\", \"code\": \"D08\", \"x\": 2520, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-39\", \"code\": \"D09\", \"x\": 2900, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-40\", \"code\": \"D10\", \"x\": 3240, \"y\": 560, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-41\", \"code\": \"E01\", \"x\": 20, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-42\", \"code\": \"E02\", \"x\": 360, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-43\", \"code\": \"E03\", \"x\": 740, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-44\", \"code\": \"E04\", \"x\": 1080, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-45\", \"code\": \"E05\", \"x\": 1460, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-46\", \"code\": \"E06\", \"x\": 1800, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-47\", \"code\": \"E07\", \"x\": 2180, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-48\", \"code\": \"E08\", \"x\": 2520, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-49\", \"code\": \"E09\", \"x\": 2900, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-50\", \"code\": \"E10\", \"x\": 3240, \"y\": 740, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-51\", \"code\": \"F01\", \"x\": 20, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-52\", \"code\": \"F02\", \"x\": 360, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-53\", \"code\": \"F03\", \"x\": 740, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-54\", \"code\": \"F04\", \"x\": 1080, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-55\", \"code\": \"F05\", \"x\": 1460, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-56\", \"code\": \"F06\", \"x\": 1800, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-57\", \"code\": \"F07\", \"x\": 2180, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-58\", \"code\": \"F08\", \"x\": 2520, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-59\", \"code\": \"F09\", \"x\": 2900, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-60\", \"code\": \"F10\", \"x\": 3240, \"y\": 920, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-61\", \"code\": \"G01\", \"x\": 20, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-62\", \"code\": \"G02\", \"x\": 360, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-63\", \"code\": \"G03\", \"x\": 740, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-64\", \"code\": \"G04\", \"x\": 1080, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-65\", \"code\": \"G05\", \"x\": 1460, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-66\", \"code\": \"G06\", \"x\": 1800, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-67\", \"code\": \"G07\", \"x\": 2180, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-68\", \"code\": \"G08\", \"x\": 2520, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-69\", \"code\": \"G09\", \"x\": 2900, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}, {\"id\": \"slot-70\", \"code\": \"G10\", \"x\": 3240, \"y\": 1100, \"w\": 300, \"h\": 160, \"status\": \"正常\", \"allowed_models\": \"\"}]}','2026-04-18 15:39:08');
/*!40000 ALTER TABLE `warehouse_layout` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `wechat_batch_summary`
--

DROP TABLE IF EXISTS `wechat_batch_summary`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `wechat_batch_summary` (
  `summary_id` char(32) COLLATE utf8mb4_general_ci NOT NULL,
  `batch_no` varchar(100) COLLATE utf8mb4_general_ci NOT NULL,
  `expected_inbound_time` datetime DEFAULT NULL,
  `model` varchar(100) COLLATE utf8mb4_general_ci NOT NULL,
  `quantity` int NOT NULL DEFAULT '0',
  `heightened` tinyint(1) NOT NULL DEFAULT '0',
  `original_batch_no` varchar(100) COLLATE utf8mb4_general_ci DEFAULT '',
  `original_expected_inbound_time` datetime DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`summary_id`),
  KEY `idx_wechat_batch_summary_batch` (`batch_no`),
  KEY `idx_wechat_batch_summary_inbound` (`expected_inbound_time`),
  KEY `idx_wechat_batch_summary_model` (`model`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `wechat_batch_summary`
--

LOCK TABLES `wechat_batch_summary` WRITE;
/*!40000 ALTER TABLE `wechat_batch_summary` DISABLE KEYS */;
/*!40000 ALTER TABLE `wechat_batch_summary` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping events for database 'rjfinshed'
--

--
-- Dumping routines for database 'rjfinshed'
--
/*!50003 DROP PROCEDURE IF EXISTS `refresh_wechat_batch_summary_all` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `refresh_wechat_batch_summary_all`()
BEGIN
  TRUNCATE TABLE `wechat_batch_summary`;

  INSERT INTO `wechat_batch_summary` (
    `summary_id`,
    `batch_no`,
    `expected_inbound_time`,
    `model`,
    `quantity`,
    `heightened`,
    `original_batch_no`,
    `original_expected_inbound_time`
  )
  SELECT
    MD5(CONCAT(
      s.`batch_no`,
      '|',
      COALESCE(DATE_FORMAT(s.`expected_inbound_time`, '%Y-%m-%d %H:%i:%s'), ''),
      '|',
      s.`model`,
      '|',
      s.`heightened`,
      '|',
      COALESCE(s.`original_batch_no`, '')
    )) AS `summary_id`,
    s.`batch_no`,
    s.`expected_inbound_time`,
    s.`model`,
    s.`quantity`,
    s.`heightened`,
    s.`original_batch_no`,
    s.`original_expected_inbound_time`
  FROM (
    SELECT
      IF(raw.`is_high`, '加高', raw.`source_batch_no`) AS `batch_no`,
      raw.`source_expected_inbound_time` AS `expected_inbound_time`,
      raw.`base_model` AS `model`,
      COUNT(*) AS `quantity`,
      IF(raw.`is_high`, 1, 0) AS `heightened`,
      IF(raw.`is_high`, raw.`source_batch_no`, '') AS `original_batch_no`,
      IF(raw.`is_high`, raw.`source_expected_inbound_time`, NULL) AS `original_expected_inbound_time`
    FROM (
      SELECT
        TRIM(`批次号`) AS `source_batch_no`,
        `预计入库时间` AS `source_expected_inbound_time`,
        TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS `base_model`,
        (
          TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
          OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'
        ) AS `is_high`
      FROM `finished_goods_data`
      WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') IS NOT NULL
        AND NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
        AND TRIM(COALESCE(`状态`, '')) = '待入库'
    ) raw
    WHERE NULLIF(raw.`base_model`, '') IS NOT NULL
    GROUP BY raw.`source_batch_no`, raw.`source_expected_inbound_time`, raw.`base_model`, raw.`is_high`
    UNION ALL
    SELECT
      IF(raw.`is_high`, '加高', '库存中') AS `batch_no`,
      CAST(NULL AS DATETIME) AS `expected_inbound_time`,
      raw.`base_model` AS `model`,
      COUNT(*) AS `quantity`,
      IF(raw.`is_high`, 1, 0) AS `heightened`,
      IF(raw.`is_high`, COALESCE(NULLIF(raw.`source_batch_no`, ''), '库存中'), '') AS `original_batch_no`,
      CAST(NULL AS DATETIME) AS `original_expected_inbound_time`
    FROM (
      SELECT
        TRIM(COALESCE(`批次号`, '')) AS `source_batch_no`,
        TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS `base_model`,
        (
          TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
          OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'
        ) AS `is_high`
      FROM `finished_goods_data`
      WHERE NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
        AND TRIM(COALESCE(`状态`, '')) = '库存中'
    ) raw
    WHERE NULLIF(raw.`base_model`, '') IS NOT NULL
    GROUP BY raw.`base_model`, raw.`is_high`, IF(raw.`is_high`, COALESCE(NULLIF(raw.`source_batch_no`, ''), '库存中'), '')
  ) s
  ON DUPLICATE KEY UPDATE
    `batch_no` = VALUES(`batch_no`),
    `expected_inbound_time` = VALUES(`expected_inbound_time`),
    `model` = VALUES(`model`),
    `quantity` = VALUES(`quantity`),
    `heightened` = VALUES(`heightened`),
    `original_batch_no` = VALUES(`original_batch_no`),
    `original_expected_inbound_time` = VALUES(`original_expected_inbound_time`);
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `refresh_wechat_batch_summary_group` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `refresh_wechat_batch_summary_group`(
  IN p_batch_no VARCHAR(100),
  IN p_expected DATETIME,
  IN p_model VARCHAR(100)
)
BEGIN
  DECLARE v_batch_no VARCHAR(100);
  DECLARE v_model VARCHAR(100);
  DECLARE v_model_base VARCHAR(100);

  SET v_batch_no = NULLIF(TRIM(COALESCE(p_batch_no, '')), '');
  SET v_model = NULLIF(TRIM(COALESCE(p_model, '')), '');
  SET v_model_base = NULLIF(TRIM(REPLACE(REPLACE(COALESCE(v_model, ''), '(加高)', ''), '加高', '')), '');

  DELETE FROM `wechat_batch_summary`
  WHERE (
      `original_batch_no` = COALESCE(v_batch_no, '')
      AND `original_expected_inbound_time` <=> p_expected
      AND `model` = v_model_base
    )
    OR (
      `batch_no` = COALESCE(v_batch_no, '')
      AND `expected_inbound_time` <=> p_expected
      AND `model` = v_model_base
      AND `heightened` = 0
    )
    OR (
      `batch_no` = '库存中'
      AND `expected_inbound_time` IS NULL
      AND `model` = v_model_base
      AND (
        `original_batch_no` = COALESCE(v_batch_no, '')
        OR COALESCE(`original_batch_no`, '') = ''
      )
    );

  IF v_batch_no IS NOT NULL AND v_model_base IS NOT NULL THEN
    INSERT INTO `wechat_batch_summary` (
      `summary_id`,
      `batch_no`,
      `expected_inbound_time`,
      `model`,
      `quantity`,
      `heightened`,
      `original_batch_no`,
      `original_expected_inbound_time`
    )
    SELECT
      MD5(CONCAT(
        s.`batch_no`,
        '|',
        COALESCE(DATE_FORMAT(s.`expected_inbound_time`, '%Y-%m-%d %H:%i:%s'), ''),
        '|',
        s.`model`,
        '|',
        s.`heightened`,
        '|',
        COALESCE(s.`original_batch_no`, '')
      )) AS `summary_id`,
      s.`batch_no`,
      s.`expected_inbound_time`,
      s.`model`,
      s.`quantity`,
      s.`heightened`,
      s.`original_batch_no`,
      s.`original_expected_inbound_time`
    FROM (
      SELECT
        IF(raw.`is_high`, '加高', raw.`source_batch_no`) AS `batch_no`,
        raw.`source_expected_inbound_time` AS `expected_inbound_time`,
        raw.`base_model` AS `model`,
        COUNT(*) AS `quantity`,
        IF(raw.`is_high`, 1, 0) AS `heightened`,
        IF(raw.`is_high`, raw.`source_batch_no`, '') AS `original_batch_no`,
        IF(raw.`is_high`, raw.`source_expected_inbound_time`, NULL) AS `original_expected_inbound_time`
      FROM (
        SELECT
          TRIM(`批次号`) AS `source_batch_no`,
          `预计入库时间` AS `source_expected_inbound_time`,
          TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS `base_model`,
          (
            TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
            OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'
          ) AS `is_high`
        FROM `finished_goods_data`
        WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') = v_batch_no
          AND `预计入库时间` <=> p_expected
          AND TRIM(REPLACE(REPLACE(TRIM(COALESCE(`机型`, '')), '(加高)', ''), '加高', '')) = v_model_base
          AND TRIM(COALESCE(`状态`, '')) = '待入库'
      ) raw
      WHERE NULLIF(raw.`base_model`, '') IS NOT NULL
      GROUP BY raw.`source_batch_no`, raw.`source_expected_inbound_time`, raw.`base_model`, raw.`is_high`
    ) s
    ON DUPLICATE KEY UPDATE
      `batch_no` = VALUES(`batch_no`),
      `expected_inbound_time` = VALUES(`expected_inbound_time`),
      `model` = VALUES(`model`),
      `quantity` = VALUES(`quantity`),
      `heightened` = VALUES(`heightened`),
      `original_batch_no` = VALUES(`original_batch_no`),
      `original_expected_inbound_time` = VALUES(`original_expected_inbound_time`);
  END IF;

  IF v_model_base IS NOT NULL THEN
    INSERT INTO `wechat_batch_summary` (
      `summary_id`,
      `batch_no`,
      `expected_inbound_time`,
      `model`,
      `quantity`,
      `heightened`,
      `original_batch_no`,
      `original_expected_inbound_time`
    )
    SELECT
      MD5(CONCAT(
        s.`batch_no`,
        '|',
        COALESCE(DATE_FORMAT(s.`expected_inbound_time`, '%Y-%m-%d %H:%i:%s'), ''),
        '|',
        s.`model`,
        '|',
        s.`heightened`,
        '|',
        COALESCE(s.`original_batch_no`, '')
      )) AS `summary_id`,
      s.`batch_no`,
      s.`expected_inbound_time`,
      s.`model`,
      s.`quantity`,
      s.`heightened`,
      s.`original_batch_no`,
      s.`original_expected_inbound_time`
    FROM (
      SELECT
        IF(raw.`is_high`, '加高', '库存中') AS `batch_no`,
        CAST(NULL AS DATETIME) AS `expected_inbound_time`,
        raw.`base_model` AS `model`,
        COUNT(*) AS `quantity`,
        IF(raw.`is_high`, 1, 0) AS `heightened`,
        IF(raw.`is_high`, COALESCE(NULLIF(raw.`source_batch_no`, ''), '库存中'), '') AS `original_batch_no`,
        CAST(NULL AS DATETIME) AS `original_expected_inbound_time`
      FROM (
        SELECT
          TRIM(COALESCE(`批次号`, '')) AS `source_batch_no`,
          TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS `base_model`,
          (
            TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
            OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'
          ) AS `is_high`
        FROM `finished_goods_data`
        WHERE TRIM(REPLACE(REPLACE(TRIM(COALESCE(`机型`, '')), '(加高)', ''), '加高', '')) = v_model_base
          AND TRIM(COALESCE(`状态`, '')) = '库存中'
      ) raw
      WHERE NULLIF(raw.`base_model`, '') IS NOT NULL
      GROUP BY raw.`base_model`, raw.`is_high`, IF(raw.`is_high`, COALESCE(NULLIF(raw.`source_batch_no`, ''), '库存中'), '')
    ) s
    ON DUPLICATE KEY UPDATE
      `batch_no` = VALUES(`batch_no`),
      `expected_inbound_time` = VALUES(`expected_inbound_time`),
      `model` = VALUES(`model`),
      `quantity` = VALUES(`quantity`),
      `heightened` = VALUES(`heightened`),
      `original_batch_no` = VALUES(`original_batch_no`),
      `original_expected_inbound_time` = VALUES(`original_expected_inbound_time`);
  END IF;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-23 14:58:01
