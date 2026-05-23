-- MySQL dump 10.13  Distrib 5.7.35, for Linux (x86_64)
--
-- Host: 30.47.14.36    Database: rjfinshed
-- ------------------------------------------------------
-- Server version	5.7.18-cynos-2.1.14-log

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `audit_log`
--

/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `audit_log` (
  `timestamp` datetime DEFAULT NULL,
  `user` varchar(255) DEFAULT NULL,
  `ip` varchar(255) DEFAULT NULL,
  `action` varchar(255) DEFAULT NULL,
  `details` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_log`
--

/*!40000 ALTER TABLE `audit_log` DISABLE KEYS */;
INSERT INTO `audit_log` VALUES ('2026-03-23 10:47:21','杨琴','Local','Upload Contract','Uploaded （33）余姚市高峰模具厂auto.doc for 余姚市低塘镇（余姚市高峰模具厂） (ID: HT202603234021)');
INSERT INTO `audit_log` VALUES ('2026-03-23 10:49:11','杨琴','Local','Upload Contract','Uploaded （35）温州宏科电子.doc for 温州市瓯海区南白象街道科创智能中心9幢201室（温州市宏科电子） (ID: HT202603236135)');
INSERT INTO `audit_log` VALUES ('2026-03-23 10:56:56','杨琴','Local','Upload Contract','Uploaded 12台州腾鸿材料科技购销合同.doc for 三门县浦坝港镇（台州腾鸿材料科技） (ID: HT202603234972)');
INSERT INTO `audit_log` VALUES ('2026-03-23 11:09:04','杨琴','Local','Upload Contract','Uploaded （29）宁海县铭优五金有限公司pro.docx for 宁海县科技园区泉水路（宁海县铭优五金） (ID: HT202603231755)');
INSERT INTO `audit_log` VALUES ('2026-03-23 11:09:34','杨琴','Local','Upload Contract','Uploaded （29）宁海县铭优五金有限公司auto.docx for 宁海县科技园区泉水路（宁海县铭优五金） (ID: HT202603238974)');
INSERT INTO `audit_log` VALUES ('2026-03-23 11:12:21','杨琴','Local','Upload Contract','Uploaded （34）余姚徐慧芳.doc for 余姚肖东镇（徐慧芳） (ID: HT202603235198)');
INSERT INTO `audit_log` VALUES ('2026-03-23 12:41:42','杨琴','Local','Upload Contract','Uploaded （36）滨海国润模具鹏.doc for 温州市龙湾区天河街道庄泉村四通路22号(陈鹏) (ID: HT202603237927)');
INSERT INTO `audit_log` VALUES ('2026-03-23 13:47:06','杨琴','Local','Upload Contract','Uploaded （30）宁波董栋.docx for 奉化区岳林东路（董栋） (ID: HT202603238244)');
INSERT INTO `audit_log` VALUES ('2026-03-23 14:38:21','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-55 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-23 14:44:50','马培培','Local','Upload Archive','Uploaded 6 photos for 96-01-516 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-23 14:45:28','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-51 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-23 14:46:02','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-52 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-23 14:46:37','马培培','Local','Upload Archive','Uploaded 66 photos for 96-02-53 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-23 14:47:11','马培培','Local','Upload Archive','Uploaded 70 photos for 96-02-54 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-23 16:42:49','朱裕玲','Local','Upload Contract','Uploaded 丹阳市开发区宇泰机械配件加工部.jpg for 镇江丹阳超华模具城（丹阳市开发区宇泰机械配件加工部） (ID: HT202603234131)');
INSERT INTO `audit_log` VALUES ('2026-03-24 08:13:39','杨琴','Local','Upload Contract','Uploaded 微信图片_20260323163503.jpg for 丹阳（丹阳开发区宇泰机械配件加工部） (ID: HT202603242192)');
INSERT INTO `audit_log` VALUES ('2026-03-24 08:49:58','杨琴','Local','Upload Contract','Uploaded 昆山辛捷合同.doc for 顺昶路（昆山辛捷机械 ） (ID: HT202603249695)');
INSERT INTO `audit_log` VALUES ('2026-03-24 09:59:00','杨琴','Local','Upload Contract','Uploaded （37）塘下郑光荣PRO.doc for 瑞安市塘下镇陈宅村天灯巷59号(郑光荣) (ID: HT202603243463)');
INSERT INTO `audit_log` VALUES ('2026-03-24 09:59:26','杨琴','Local','Upload Contract','Uploaded （37）塘下郑光荣Auto.doc for 瑞安市塘下镇陈宅村天灯巷59号(郑光荣) (ID: HT202603246141)');
INSERT INTO `audit_log` VALUES ('2026-03-24 10:00:29','杨琴','Local','Upload Contract','Uploaded （38）塘下郑阿旦.doc for 瑞安市塘下镇沙河村沙河路4巷5号(郑光旦) (ID: HT202603247721)');
INSERT INTO `audit_log` VALUES ('2026-03-24 10:51:57','杨琴','Local','Upload Contract','Uploaded 昆山瑞丰隆合同.doc for 进发路（昆山瑞丰隆机械） (ID: HT202603247531)');
INSERT INTO `audit_log` VALUES ('2026-03-24 10:55:51','杨琴','Local','Upload Contract','Uploaded 上海闳 显合同.doc for 无锡市新吴区长江东路（上海闳显机电） (ID: HT202603242411)');
INSERT INTO `audit_log` VALUES ('2026-03-24 10:56:13','杨琴','Local','Upload Contract','Uploaded 上海闳显合同.doc for 无锡市新吴区长江东路（上海闳显机电） (ID: HT202603246302)');
INSERT INTO `audit_log` VALUES ('2026-03-24 11:13:56','杨琴','Local','Upload Contract','Uploaded （17）南皮宫杰.doc for 河北省南皮县南皮镇穆三卜村（宫杰） (ID: HT202603241194)');
INSERT INTO `audit_log` VALUES ('2026-03-24 11:15:26','杨琴','Local','Upload Contract','Uploaded 武汉鑫宝科合同.doc for 句容市致远路（武汉鑫宝科机械） (ID: HT202603249263)');
INSERT INTO `audit_log` VALUES ('2026-03-24 11:16:12','杨琴','Local','Upload Contract','Uploaded （37）宁波平头哥精密五金.doc for 余姚临山镇（宁波市平头哥精密五金） (ID: HT202603243656)');
INSERT INTO `audit_log` VALUES ('2026-03-24 11:23:58','杨琴','Local','Upload Contract','Uploaded （39）瑞安汇特传动部件auto.doc for 瑞安市上望街道匠心路1号(瑞安市汇特传动部件) (ID: HT202603248499)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:20:21','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-118 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:21:16','马培培','Local','Upload Archive','Uploaded 77 photos for 96-01-575 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:21:48','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-576 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:22:18','马培培','Local','Upload Archive','Uploaded 79 photos for 96-01-582 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:23:11','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-01 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:23:39','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-02 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:24:08','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-03 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:24:35','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-04 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:25:11','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-564 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:25:40','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-565 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:26:10','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-566 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:26:39','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-567 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:27:06','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-568 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:27:39','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-571 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:28:37','马培培','Local','Upload Archive','Uploaded 79 photos for 96-01-572 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:29:04','马培培','Local','Upload Archive','Uploaded 79 photos for 96-01-573 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:29:38','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-574 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:30:06','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-580 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:30:37','马培培','Local','Upload Archive','Uploaded 77 photos for 96-01-581 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:31:19','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-114 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:31:56','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-115 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:32:24','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-116 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:32:51','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-117 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:33:33','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-119 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:34:12','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-120 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:34:38','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-121 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:35:06','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-122 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:35:34','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-123 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:36:11','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-124 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:36:38','马培培','Local','Upload Archive','Uploaded 67 photos for 96-02-125 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:37:11','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-126 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:37:38','马培培','Local','Upload Archive','Uploaded 67 photos for 96-02-127 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:38:06','马培培','Local','Upload Archive','Uploaded 67 photos for 96-02-128 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:38:34','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-129 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:39:11','马培培','Local','Upload Archive','Uploaded 84 photos for 95-05-137 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:55:14','杨琴','Local','Upload Contract','Uploaded 常州纪铭易合同.doc for 常州前黄（常州纪铭易机械） (ID: HT202603246029)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:57:08','杨琴','Local','Upload Contract','Uploaded 昆山冠业杰合同.doc for 东定路（昆山冠业杰科技） (ID: HT202603245731)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:58:00','杨琴','Local','Upload Contract','Uploaded 昆山好易为合同.doc for 张浦欣达路（昆山好易为智能） (ID: HT202603243407)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:58:57','杨琴','Local','Upload Contract','Uploaded 苏州麦凯西合同.doc for 常熟支塘镇（苏州麦凯西流体技术） (ID: HT202603246375)');
INSERT INTO `audit_log` VALUES ('2026-03-24 12:58:58','杨琴','Local','Upload Contract','Uploaded 苏州麦凯西合同.doc for 常熟支塘镇（苏州麦凯西流体技术） (ID: HT202603244508)');
INSERT INTO `audit_log` VALUES ('2026-03-24 13:00:28','杨琴','Local','Upload Contract','Uploaded 王正中（湖南飘风）.doc for 湖南省汨罗市神鼎山镇（王正中-湖南飘风） (ID: HT202603244488)');
INSERT INTO `audit_log` VALUES ('2026-03-24 13:01:30','杨琴','Local','Upload Contract','Uploaded 武汉百则合同23.doc for 武汉市蔡甸区海天汽配城（武汉百则-武汉诚利德） (ID: HT202603242955)');
INSERT INTO `audit_log` VALUES ('2026-03-24 13:02:44','杨琴','Local','Upload Contract','Uploaded 苏州汇雄合同.doc for 吴江菀坪（苏州汇雄电子） (ID: HT202603241388)');
INSERT INTO `audit_log` VALUES ('2026-03-24 13:05:18','杨琴','Local','Upload Contract','Uploaded （41）温州陈保标.doc for 温州市龙湾区滨海九路金海一道，农科小微园5栋3楼（陈保标） (ID: HT202603246183)');
INSERT INTO `audit_log` VALUES ('2026-03-24 13:06:12','杨琴','Local','Upload Contract','Uploaded （31）宁波济福模具有限公司.docx for 宁海模具城（宁波济福模具） (ID: HT202603241487)');
INSERT INTO `audit_log` VALUES ('2026-03-24 13:07:11','杨琴','Local','Upload Contract','Uploaded （40）瑞安创衡模具.doc for 瑞安市塘下镇凤都二路181号（瑞安创衡模具） (ID: HT202603244276)');
INSERT INTO `audit_log` VALUES ('2026-03-24 13:12:02','杨琴','Local','Upload Contract','Uploaded 苏州创隆合同.doc for 吴江同里（苏州创隆模具） (ID: HT202603247099)');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:28:52','马培培','Local','Upload Archive','Uploaded 68 photos for 96-01-603 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:29:58','马培培','Local','Delete Archive Photo','Deleted 其他_66_20260319_202419.jpg from 96-01-380');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:30:00','马培培','Local','Delete Archive Photo','Deleted 其他_65_20260319_202419.jpg from 96-01-380');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:30:01','马培培','Local','Delete Archive Photo','Deleted 其他_64_20260319_202419.jpg from 96-01-380');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:30:32','马培培','Local','Upload Archive','Uploaded 5 photos for 96-01-380 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:30:52','马培培','Local','Upload Archive','Uploaded 77 photos for 96-01-583 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:31:20','马培培','Local','Delete Archive Photo','Deleted 其他_56_20260320_142444.jpg from 96-02-65');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:31:21','马培培','Local','Delete Archive Photo','Deleted 其他_55_20260320_142444.jpg from 96-02-65');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:31:22','马培培','Local','Delete Archive Photo','Deleted 其他_54_20260320_142444.jpg from 96-02-65');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:31:47','马培培','Local','Upload Archive','Uploaded 5 photos for 96-02-65 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 14:33:22','马培培','Local','Upload Archive','Uploaded 60 photos for 96-02-78 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 16:32:13','杨琴','Local','Upload Contract','Uploaded 湖南王正中合同8.doc for 湖南省长沙市岳麓区东方红中路（王正中-长沙湘溯） (ID: HT202603241266)');
INSERT INTO `audit_log` VALUES ('2026-03-24 16:45:40','杨琴','Local','Upload Contract','Uploaded 陈平原合同.doc for 陆杨（陈平原 ） (ID: HT202603247065)');
INSERT INTO `audit_log` VALUES ('2026-03-24 19:01:35','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-253 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 19:16:01','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-139 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-24 19:16:31','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-45 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-25 08:31:47','杨琴','Local','Delete Contract File','Deleted 苏州迅科合同.doc from HT202603196699');
INSERT INTO `audit_log` VALUES ('2026-03-25 08:32:26','杨琴','Local','Upload Contract','Uploaded 苏州迅科合同.doc for 优德路（苏州迅科模具） (ID: HT202603196699)');
INSERT INTO `audit_log` VALUES ('2026-03-25 08:33:37','杨琴','Local','Upload Contract','Uploaded 吴松合同26-03.doc for 南港机场路(吴松 ) (ID: HT202603257199)');
INSERT INTO `audit_log` VALUES ('2026-03-25 09:28:11','杨琴','Local','Upload Contract','Uploaded 更改：广东办事处样机下单表（3.26批次）.pdf for 东莞南城（东莞宏轩） (ID: HT202603259919)');
INSERT INTO `audit_log` VALUES ('2026-03-25 10:09:04','杨琴','Local','Upload Contract','Uploaded 乐清华邦企业购销合同.doc for 乐清市北白象镇重石工业园区（乐清华邦企业） (ID: HT202603253764)');
INSERT INTO `audit_log` VALUES ('2026-03-25 10:57:11','杨琴','Local','Upload Contract','Uploaded （11）邢台张书宁.doc for 河北省邢台市广宗县冯家寨镇东霍城寨村（张书宁） (ID: HT202603252824)');
INSERT INTO `audit_log` VALUES ('2026-03-25 12:54:18','杨琴','Local','Upload Contract','Uploaded 昆山新捷讯 合同.doc for 新浦路（昆山新捷讯机械） (ID: HT202603256346)');
INSERT INTO `audit_log` VALUES ('2026-03-25 13:05:02','杨琴','Local','Upload Contract','Uploaded 昆山铭云生合同.doc for 环庆路（昆山铭云生科技） (ID: HT202603258269)');
INSERT INTO `audit_log` VALUES ('2026-03-25 13:06:00','杨琴','Local','Upload Contract','Uploaded 昆山泽匠合同.doc for 东盛路（昆山泽匠机械 ） (ID: HT202603252888)');
INSERT INTO `audit_log` VALUES ('2026-03-25 13:06:49','杨琴','Local','Upload Contract','Uploaded 天长市银佳合同.doc for 安徽省天长市秦楠镇第二工业园区（天长市银佳电气） (ID: HT202603251928)');
INSERT INTO `audit_log` VALUES ('2026-03-25 13:07:50','杨琴','Local','Upload Contract','Uploaded 常州佳驰 合同.doc for 新北薛家北漕河路（常州佳驰机械 ） (ID: HT202603253210)');
INSERT INTO `audit_log` VALUES ('2026-03-25 13:08:46','杨琴','Local','Upload Contract','Uploaded 昆山沃德利合同.doc for 灯塔路（昆山沃德利模具） (ID: HT202603258506)');
INSERT INTO `audit_log` VALUES ('2026-03-25 15:17:22','杨琴','Local','Upload Contract','Uploaded （40）余姚马灵灵.doc for 余姚模具城（马灵灵） (ID: HT202603256315)');
INSERT INTO `audit_log` VALUES ('2026-03-25 15:21:23','杨琴','Local','Upload Contract','Uploaded （39）宁波甲木模具.doc for 余姚泗门镇（宁波甲木模具） (ID: HT202603254775)');
INSERT INTO `audit_log` VALUES ('2026-03-25 15:22:29','杨琴','Local','Upload Contract','Uploaded （38）宁波市志鑫模具.doc for 余姚同光村（宁波市志鑫模具） (ID: HT202603254632)');
INSERT INTO `audit_log` VALUES ('2026-03-25 16:20:02','杨琴','Local','Upload Contract','Uploaded 昆山云悦合同.doc for 张浦振兴路（昆山云悦模具 ） (ID: HT202603252720)');
INSERT INTO `audit_log` VALUES ('2026-03-25 16:20:48','杨琴','Local','Upload Contract','Uploaded 滁州佳乐合同.doc for 滁州市来安县经济开发区中央大道（滁州佳乐精密配件） (ID: HT202603259177)');
INSERT INTO `audit_log` VALUES ('2026-03-25 16:20:55','杨琴','Local','Upload Contract','Uploaded 滁州佳乐合同.doc for 滁州市来安县经济开发区中央大道（滁州佳乐精密配件） (ID: HT202603256992)');
INSERT INTO `audit_log` VALUES ('2026-03-25 16:45:54','杨琴','Local','Upload Contract','Uploaded 下单表-天津市航亚科技有限公司.doc for 天津武清区曹子里镇（天津市航亚科技） (ID: HT202603252740)');
INSERT INTO `audit_log` VALUES ('2026-03-25 16:47:55','杨琴','Local','Upload Contract','Uploaded 2026下单表 韩国 2 台.doc for 韩国 (ID: HT202603258174)');
INSERT INTO `audit_log` VALUES ('2026-03-26 10:46:32','杨琴','Local','Upload Contract','Uploaded （32）宁波长铸精密模具.docx for 宁波市宁海县跃龙街道模具城H25幢（宁波长铸精密模具） (ID: HT202603269801)');
INSERT INTO `audit_log` VALUES ('2026-03-26 10:47:12','杨琴','Local','Upload Contract','Uploaded （44）瓯海卢忠建.doc for 温州市瓯海经济开发区东经二路3号（卢忠建） (ID: HT202603267437)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:16:58','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-235 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:17:38','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-236 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:18:14','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-237 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:18:45','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-238 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:19:55','马培培','Local','Upload Archive','Uploaded 67 photos for 96-02-227 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:20:29','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-234 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:22:42','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-241 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:23:14','马培培','Local','Upload Archive','Uploaded 69 photos for 96-02-245 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:23:47','马培培','Local','Upload Archive','Uploaded 68 photos for 96-01-387 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:24:34','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-232 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:25:05','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-233 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:25:35','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-239 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:26:20','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-23 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:27:37','马培培','Local','Upload Archive','Uploaded 5 photos for 96-01-437 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:27:54','马培培','Local','Upload Archive','Uploaded 70 photos for 96-01-604 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:28:52','马培培','Local','Upload Archive','Uploaded 70 photos for 96-02-240 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:30:06','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-07 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:30:38','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-08 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:31:09','马培培','Local','Upload Archive','Uploaded 77 photos for 96-02-09 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:31:59','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-10 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:32:34','马培培','Local','Upload Archive','Uploaded 77 photos for 96-02-15 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:33:06','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-16 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:33:38','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-17 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:34:10','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-18 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:34:47','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-19 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:35:19','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-20 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:35:53','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-24 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:36:30','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-25 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:37:04','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-26 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:37:49','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-27 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:38:30','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-46 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:39:07','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-138 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:39:36','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-140 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:40:11','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-228 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:41:20','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-229 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:42:00','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-230 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 14:42:42','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-231 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-26 15:11:06','杨琴','Local','Upload Contract','Uploaded 广东办事处样机下单表（3.28批次）.pdf for 东莞南城（东莞宏轩） (ID: HT202603269402)');
INSERT INTO `audit_log` VALUES ('2026-03-26 15:24:30','杨琴','Local','Upload Contract','Uploaded 下单表-青岛嘉盈.doc for 山东省青岛市城阳区臻园路8号（山东省青岛市城阳区臻园路8号） (ID: HT202603263072)');
INSERT INTO `audit_log` VALUES ('2026-03-26 15:25:31','杨琴','Local','Upload Contract','Uploaded 下单表-张俊平 3台FR400.doc for 天津津南区双港工业园（张俊平） (ID: HT202603268360)');
INSERT INTO `audit_log` VALUES ('2026-03-26 15:26:21','杨琴','Local','Upload Contract','Uploaded 下单表-张俊平1台FR500.doc for 天津津南区双港工业园（张俊平） (ID: HT202603269464)');
INSERT INTO `audit_log` VALUES ('2026-03-26 15:27:29','杨琴','Local','Upload Contract','Uploaded 下单表600Auto.doc for 山东省青岛市即墨区温泉二路7-1号 青岛国际博览中心 E2 馆（王丹伟--- 张凯） (ID: HT202603264861)');
INSERT INTO `audit_log` VALUES ('2026-03-26 16:33:16','杨琴','Local','Upload Contract','Uploaded （46）滨海刘志强.doc for 滨海三道12路高翔工业园3栋一楼（刘志强） (ID: HT202603261624)');
INSERT INTO `audit_log` VALUES ('2026-03-26 16:35:48','杨琴','Local','Upload Contract','Uploaded 苏州馨新旭合同.doc for 胥口(苏州馨新旭机械) (ID: HT202603269049)');
INSERT INTO `audit_log` VALUES ('2026-03-26 16:36:42','杨琴','Local','Upload Contract','Uploaded 昆山祥昆达合同.doc for 恒盛路（昆山祥昆达机械） (ID: HT202603267153)');
INSERT INTO `audit_log` VALUES ('2026-03-26 16:38:03','杨琴','Local','Upload Contract','Uploaded 昆山祥昆达 合同.doc for 恒盛路（昆山祥昆达机械） (ID: HT202603265389)');
INSERT INTO `audit_log` VALUES ('2026-03-26 16:39:34','杨琴','Local','Upload Contract','Uploaded 昆山恒全辉合同.doc for 张浦博伟路（昆山恒全辉模具） (ID: HT202603268688)');
INSERT INTO `audit_log` VALUES ('2026-03-27 08:08:09','杨琴','Local','Upload Contract','Uploaded 昆山万品胜合同.doc for 康庄路(昆山万品胜模具  ) (ID: HT202603271199)');
INSERT INTO `audit_log` VALUES ('2026-03-27 08:12:31','杨琴','Local','Upload Contract','Uploaded （45）滨海桂云.doc for 温州市龙湾区滨海园区一道14路庄泉电器创业园(桂云） (ID: HT202603277886)');
INSERT INTO `audit_log` VALUES ('2026-03-27 08:31:49','杨琴','Local','Upload Contract','Uploaded （8）湖州精匠精密模具.doc for 湖州德清雷甸镇明珠大道199号2幢1楼AB区（湖州精匠精密模具） (ID: HT202603274127)');
INSERT INTO `audit_log` VALUES ('2026-03-27 10:00:06','杨琴','Local','Upload Contract','Uploaded （32）宁海县金旵模具加工店.docx for 宁海县新兴工业C区金山六路9号(宁海县金旵模具加工店) (ID: HT202603277487)');
INSERT INTO `audit_log` VALUES ('2026-03-27 10:34:51','杨琴','Local','Upload Contract','Uploaded 常州瑞研合同.doc for 常州市新北区孟河镇望江路(常州瑞研精密设备 ) (ID: HT202603273547)');
INSERT INTO `audit_log` VALUES ('2026-03-27 11:08:14','杨琴','Local','Upload Contract','Uploaded 刘庆兵合同.doc for 蓬朗镇（刘庆兵） (ID: HT202603277800)');
INSERT INTO `audit_log` VALUES ('2026-03-27 11:21:13','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-05 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 11:22:07','马培培','Local','Upload Archive','Uploaded 70 photos for 96-02-249 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 11:23:03','马培培','Local','Upload Archive','Uploaded 5 photos for 96-01-438 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:10:37','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-06 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:11:14','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-11 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:11:57','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-12 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:12:27','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-13 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:12:59','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-14 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:13:34','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-21 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:14:07','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-22 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:14:40','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-87 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:15:10','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-88 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:15:47','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-89 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:16:22','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-90 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:16:56','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-95 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:17:33','马培培','Local','Upload Archive','Uploaded 79 photos for 96-01-584 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:18:05','马培培','Local','Upload Archive','Uploaded 78 photos for 96-01-585 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:19:08','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-101 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:19:45','马培培','Local','Upload Archive','Uploaded 78 photos for 96-02-102 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:20:24','马培培','Local','Upload Archive','Uploaded 79 photos for 96-02-103 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:21:03','马培培','Local','Upload Archive','Uploaded 72 photos for 96-02-136 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:21:35','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-137 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:23:10','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-133 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:23:41','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-134 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:24:21','马培培','Local','Upload Archive','Uploaded 68 photos for 96-02-135 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:44:54','杨琴','Local','Upload Contract','Uploaded （16）金华谢志龙.doc for 浙江省金华市浙中模具城C区6栋26号（谢志龙） (ID: HT202603272418)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:45:56','杨琴','Local','Upload Contract','Uploaded （34）浙江盈峰光通信科技auto.docx for 宁海县西店镇滨海工业园区（浙江盈峰光通信科技） (ID: HT202603273304)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:46:19','杨琴','Local','Upload Contract','Uploaded （34）浙江盈峰光通信科技pro.docx for 宁海县西店镇滨海工业园区（浙江盈峰光通信科技） (ID: HT202603278646)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:47:26','杨琴','Local','Upload Contract','Uploaded （17）永康朱海艇.doc for 永康市神州模具城B1幢8号（朱海艇） (ID: HT202603271630)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:48:40','杨琴','Local','Upload Contract','Uploaded （18）缙云麻群妃.doc for 丽水市缙云县新碧黄碧街（麻群妃） (ID: HT202603279927)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:48:55','杨琴','Local','Upload Contract','Uploaded （18）缙云麻群妃.doc for 丽水市缙云县新碧黄碧街（麻群妃） (ID: HT202603278869)');
INSERT INTO `audit_log` VALUES ('2026-03-27 12:49:54','杨琴','Local','Upload Contract','Uploaded 无锡健马合同.doc for 宜兴市新庄街道新西路（无锡健马机械） (ID: HT202603274550)');
INSERT INTO `audit_log` VALUES ('2026-03-27 13:02:29','杨琴','Local','Upload Contract','Uploaded 常州创臻合同.doc for 常州五一路（常州创臻精工） (ID: HT202603278375)');
INSERT INTO `audit_log` VALUES ('2026-03-27 13:12:46','杨琴','Local','Upload Contract','Uploaded 江苏乾亚合同.doc for 宿迁市泗洪县纬六路（江苏乾亚汽车零部件） (ID: HT202603275953)');
INSERT INTO `audit_log` VALUES ('2026-03-27 13:53:13','杨琴','Local','Upload Contract','Uploaded 昆山铭利成合同.doc for 朱家湾路（昆山铭利成精密组件） (ID: HT202603272311)');
INSERT INTO `audit_log` VALUES ('2026-03-27 15:12:46','杨琴','Local','Upload Contract','Uploaded （47）温州鼎联模具科技pro.doc for 温州经济技术开发区星海街道滨海一道1156号（温州鼎联模具科技） (ID: HT202603272160)');
INSERT INTO `audit_log` VALUES ('2026-03-27 15:13:06','杨琴','Local','Upload Contract','Uploaded （47）温州鼎联模具科技auto.doc for 温州经济技术开发区星海街道滨海一道1156号（温州鼎联模具科技） (ID: HT202603273537)');
INSERT INTO `audit_log` VALUES ('2026-03-27 15:20:15','马培培','Local','Upload Archive','Uploaded 71 photos for 96-02-141 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-03-27 16:54:27','杨琴','Local','Upload Contract','Uploaded （13）翔宇模具配件厂.doc for 重庆九龙坡华岩华岩村6号附15号（九龙坡区九龙园区翔宇模具） (ID: HT202603277971)');
INSERT INTO `audit_log` VALUES ('2026-03-27 16:58:01','杨琴','Local','Upload Contract','Uploaded （14）海宁市力佳隆门窗.doc for 嘉兴市海宁市经编十路27号（海宁市力佳隆门窗密封条） (ID: HT202603274740)');
INSERT INTO `audit_log` VALUES ('2026-04-04 15:58:38','System','Local','Batch Delete Archive Photo','Deleted 34 photos from 95-12-435');
INSERT INTO `audit_log` VALUES ('2026-04-04 15:58:54','System','Local','Batch Delete Archive Photo','Deleted 4 photos from 95-12-435');
INSERT INTO `audit_log` VALUES ('2026-04-04 16:00:42','System','Local','Batch Delete Archive Photo','Deleted 25 photos from 95-12-435');
INSERT INTO `audit_log` VALUES ('2026-04-04 16:00:53','System','Local','Batch Delete Archive Photo','Deleted 61 photos from 95-12-433');
INSERT INTO `audit_log` VALUES ('2026-04-04 16:01:30','System','Local','Batch Delete Archive Photo','Deleted 60 photos from 95-12-434');
INSERT INTO `audit_log` VALUES ('2026-04-04 16:06:15','System','Local','Upload Archive','Uploaded 14 photos for 95-12-434 (Wheel:, Motor:)');
INSERT INTO `audit_log` VALUES ('2026-04-04 16:18:33','System','Local','Batch Delete Archive Photo','Deleted 15 photos from 95-12-434');
INSERT INTO `audit_log` VALUES ('2026-04-04 16:18:37','System','Local','Batch Delete Archive Photo','Deleted 1 photos from 95-12-434');
INSERT INTO `audit_log` VALUES ('2026-04-06 19:20:59','System','Local','Upload Machine Archive','96-03-96: uploaded 9 files');
INSERT INTO `audit_log` VALUES ('2026-04-06 19:39:51','System','Local','Upload Machine Archive','96-03-98: uploaded 13 files');
INSERT INTO `audit_log` VALUES ('2026-04-08 14:48:12','系统管理员','Local','Upload Contract','Uploaded 下单表--山东临朐 和昭.docx for 山东省潍坊市临朐县奔月路与025县道交叉口南100米（临朐和昭模具） (ID: HT202604082053)');
INSERT INTO `audit_log` VALUES ('2026-04-10 12:06:10','System','Local','Upload Machine Archive','96-04-1: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 12:16:36','System','Local','Upload Machine Archive','93-10-01: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 12:16:51','System','Local','Delete Machine Archive','93-10-01: deleted 档案图片_1_20260413_121636.jpg');
INSERT INTO `audit_log` VALUES ('2026-04-13 12:17:04','System','Local','Upload Machine Archive','93-10-01: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 12:17:09','System','Local','Delete Machine Archive','93-10-01: deleted 档案图片_1_20260413_121704.jpg');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:01:26','System','Local','Upload Machine Archive','93-10-01: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:01:28','System','Local','Delete Machine Archive','93-10-01: deleted 档案图片_1_20260413_130126.jpg');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:35:30','System','Local','Upload Machine Archive','96-01-335: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:39:43','System','Local','Delete Machine Archive','96-01-335: deleted 档案图片_1_20260413_133530.jpg');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:39:49','System','Local','Upload Machine Archive','96-01-335: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:39:58','System','Local','Delete Machine Archive','96-01-335: deleted 档案图片_1_20260413_133949.jpg');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:40:24','System','Local','Upload Machine Archive','96-01-335: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:45:26','System','Local','Delete Machine Archive','96-01-335: deleted 档案图片_1_20260413_134024.jpg');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:45:34','System','Local','Upload Machine Archive','96-01-335: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 13:51:37','System','Local','Upload Machine Archive','96-02-11: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:10:34','System','Local','Batch Delete Machine Archive','96-03-98: deleted 13 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:12:22','System','Local','Upload Machine Archive','96-01-380: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:17:56','System','Local','Upload Machine Archive','96-02-11: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:18:07','System','Local','Upload Machine Archive','96-02-78: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:23:46','System','Local','Upload Machine Archive','96-02-11: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:24:05','System','Local','Upload Machine Archive','96-02-11: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:35:55','System','Local','Upload Machine Archive','96-02-11: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:38:16','System','Local','Upload Machine Archive','96-02-239: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:45:27','System','Local','Upload Machine Archive','96-01-380: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:45:34','System','Local','Upload Machine Archive','96-01-380: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:45:40','System','Local','Upload Machine Archive','96-01-380: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:46:28','System','Local','Upload Machine Archive','96-02-78: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:47:02','System','Local','Upload Machine Archive','96-01-380: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 14:53:59','System','Local','Upload Machine Archive','96-02-244: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:04:17','System','Local','Upload Machine Archive','96-03-378: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:41:18','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:43:30','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:43:34','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:43:38','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:43:42','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:43:46','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:43:50','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 15:43:54','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-13 16:01:37','System','Local','Upload Machine Archive','96-02-14: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-18 09:48:50','System','Local','Upload Machine Archive','96-03-70: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-18 13:18:18','System','Local','Upload Machine Archive','96-03-348: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-18 13:18:43','System','Local','Upload Machine Archive','96-03-348: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-18 13:19:23','System','Local','Upload Machine Archive','96-04-254: uploaded 1 files');
INSERT INTO `audit_log` VALUES ('2026-04-18 13:30:08','Web','Local','Upload Contract','Uploaded B 机成品数据全栈集成服务项目立项报告.docx for test418 (ID: HT202604181492)');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:25:27','系统管理员','127.0.0.1','用户管理-更新','更新用户 xiaozhu，字段: role, status, name');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:29:38','朱孝二','127.0.0.1','订单配货-锁定','订单 SO-20260418-E3A1 配货 1 台，流水号: 96-04-257');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:29:49','朱孝二','127.0.0.1','订单配货-锁定','订单 SO-20260418-E3A1 配货 7 台，流水号: 96-04-251, 96-04-252, 96-04-253, 96-04-258, 96-04-259, 96-04-260, 96-04-261');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:30:33','朱孝二','127.0.0.1','订单配货-锁定','订单 SO-20260408-07CB 配货 1 台，流水号: 96-04-282');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:36:26','朱孝二','127.0.0.1','订单配货-锁定','订单 SO-20260418-99A0 配货 2 台，流水号: 96-04-158, 95-04-222');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:37:22','朱孝二','127.0.0.1','订单配货-锁定','订单 SO-20260418-52B6 配货 1 台，流水号: 96-04-262');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:41:19','朱孝二','127.0.0.1','订单配货-锁定','订单 SO-20260418-A436 配货 1 台，流水号: 96-04-24');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:41:42','朱孝二','127.0.0.1','订单配货-锁定','订单 SO-20260418-A436 配货 5 台，流水号: 96-04-26, 96-04-25, 96-04-23, 96-03-350, 96-03-351');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:57:04','系统管理员','127.0.0.1','销售下单-生成订单','生成订单 SO-20260418-516F，客户: 天津津南区双港工业园（宇成明佳--李晓磊），数量: 1');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:57:04','系统管理员','127.0.0.1','合同管理-更新状态','合同 HT202603148359 状态更新为 已下单');
INSERT INTO `audit_log` VALUES ('2026-04-18 15:57:21','系统管理员','127.0.0.1','销售下单-生成订单','生成订单 SO-20260418-C7AC，客户: 11，数量: 1');
INSERT INTO `audit_log` VALUES ('2026-04-18 16:20:11','TraeProbe','127.0.0.1','排查测试-写入验证','manual probe');
/*!40000 ALTER TABLE `audit_log` ENABLE KEYS */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-19 16:34:23



-- MySQL dump 10.13  Distrib 5.7.35, for Linux (x86_64)
--
-- Host: 30.47.14.36    Database: rjfinshed
-- ------------------------------------------------------
-- Server version	5.7.18-cynos-2.1.14-log

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `dealer_applications`
--

/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `dealer_applications` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
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
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dealer_applications`
--

/*!40000 ALTER TABLE `dealer_applications` DISABLE KEYS */;
INSERT INTO `dealer_applications` VALUES (1,'dealer-1779101975701','瑞钧智科','13506234097','朱孝一','常熟','regional_manager','','王总小助理','approved','2026-05-18 10:59:35','2026-05-18 10:59:58');
INSERT INTO `dealer_applications` VALUES (2,'dealer-1779102056789','12','10000','小李','江苏苏州','dealer','瑞钧智科','','approved','2026-05-18 11:00:56','2026-05-18 11:01:19');
INSERT INTO `dealer_applications` VALUES (3,'dealer-1779172171086','农副产品加工厂','10086','朱宸','华东','dealer','瑞钧智科','无','approved','2026-05-19 06:29:31','2026-05-19 06:35:19');
/*!40000 ALTER TABLE `dealer_applications` ENABLE KEYS */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-19 16:34:23



-- MySQL dump 10.13  Distrib 5.7.35, for Linux (x86_64)
--
-- Host: 30.47.14.36    Database: rjfinshed
-- ------------------------------------------------------
-- Server version	5.7.18-cynos-2.1.14-log

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `dealer_orders`
--

/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `dealer_orders` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `order_no` varchar(64) NOT NULL,
  `line_no` int(11) NOT NULL DEFAULT '1',
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
  `quantity` int(11) NOT NULL DEFAULT '1',
  `approved_qty` int(11) NOT NULL DEFAULT '0',
  `allocated_qty` int(11) NOT NULL DEFAULT '0',
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
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dealer_order_line` (`order_no`,`line_no`),
  KEY `idx_dealer_order_no` (`order_no`),
  KEY `idx_dealer_id` (`dealer_id`),
  KEY `idx_status` (`status`),
  KEY `idx_batch_model_status` (`batch_no`,`model`,`status`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `dealer_orders`
--

/*!40000 ALTER TABLE `dealer_orders` DISABLE KEYS */;
INSERT INTO `dealer_orders` VALUES (1,'DO202605181103301476',1,'dealer-1779102056789','12','10000','瑞钧智科','12','qw','11','FR-400XS(PRO)','FINISHED-STOCK','现货','finished',2,0,0,'12','','pending','pending',NULL,'',NULL,NULL,'','','',NULL,'2026-05-18 11:03:30','2026-05-18 11:03:30');
INSERT INTO `dealer_orders` VALUES (2,'DO202605181138474216',1,'dealer-1779101975701','瑞钧智科','13506234097','瑞钧智科','kddd','朱孝一','13506234097','FR-8060XS(PRO)','FINISHED-STOCK','现货','finished',2,0,0,'6/10','不要水箱','pending','approved','老板亲自体验','瑞钧智科','2026-05-18 19:40:07',NULL,'','','',NULL,'2026-05-18 11:38:47','2026-05-18 11:40:07');
INSERT INTO `dealer_orders` VALUES (3,'DO202605181138474216',2,'dealer-1779101975701','瑞钧智科','13506234097','瑞钧智科','kddd','朱孝一','13506234097','FR-1100XS(PRO)','FINISHED-STOCK','现货','finished',1,0,0,'6/10','不要水箱','pending','approved','老板亲自体验','瑞钧智科','2026-05-18 19:40:07',NULL,'','','',NULL,'2026-05-18 11:38:47','2026-05-18 11:40:07');
INSERT INTO `dealer_orders` VALUES (4,'DO202605181138474216',3,'dealer-1779101975701','瑞钧智科','13506234097','瑞钧智科','kddd','朱孝一','13506234097','FR-8060Y','05-05附加','2026-06-29','wip',1,0,0,'6/10','不要水箱','pending','approved','老板亲自体验','瑞钧智科','2026-05-18 19:40:07',NULL,'','','',NULL,'2026-05-18 11:38:47','2026-05-18 11:40:07');
INSERT INTO `dealer_orders` VALUES (5,'DO202605181138474216',4,'dealer-1779101975701','瑞钧智科','13506234097','瑞钧智科','kddd','朱孝一','13506234097','FR-600AUTO','05-10','2026-05-31','wip',10,0,0,'6/10','不要水箱','pending','approved','老板亲自体验','瑞钧智科','2026-05-18 19:40:07',NULL,'','','',NULL,'2026-05-18 11:38:47','2026-05-18 11:40:07');
INSERT INTO `dealer_orders` VALUES (6,'DO202605181138546875',1,'dealer-1779102056789','12','10000','瑞钧智科','a a','啊啊','22','FR-400XS(PRO)','FINISHED-STOCK','现货','finished',1,0,0,'383','','pending','approved','','瑞钧智科','2026-05-18 19:39:43',NULL,'','','',NULL,'2026-05-18 11:38:54','2026-05-18 11:39:43');
INSERT INTO `dealer_orders` VALUES (8,'DO202605190644025540',1,'dealer-1779172171086','农副产品加工厂','10086','瑞钧智科','cj','cj','12484648424','FR-400XS(PRO)','','','',52,0,0,'','','regional_rejected','rejected','','瑞钧智科','2026-05-19 14:44:27',NULL,'','','',NULL,'2026-05-19 06:44:02','2026-05-19 06:44:27');
INSERT INTO `dealer_orders` VALUES (14,'DO202605190646278410',1,'dealer-1779172171086','农副产品加工厂','10086','瑞钧智科','cj','cj','911','FL-8560XS(PRO)(加高)','03-03附加','2026-05-09','heightened',1,0,0,'','','pending','approved','','瑞钧智科','2026-05-19 15:27:57',NULL,'','','',NULL,'2026-05-19 07:27:57','2026-05-19 07:27:57');
INSERT INTO `dealer_orders` VALUES (15,'DO202605190646278410',2,'dealer-1779172171086','农副产品加工厂','10086','瑞钧智科','cj','cj','911','FR-600XS(PRO)','04-19','2026-05-10','wip',2,0,0,'','','pending','approved','','瑞钧智科','2026-05-19 15:27:57',NULL,'','','',NULL,'2026-05-19 07:27:57','2026-05-19 07:27:57');
INSERT INTO `dealer_orders` VALUES (16,'DO202605190646278410',3,'dealer-1779172171086','农副产品加工厂','10086','瑞钧智科','cj','cj','911','FR-500XS(PRO)(加高)','05-11','2026-06-01','heightened',3,0,0,'','','pending','approved','','瑞钧智科','2026-05-19 15:27:57',NULL,'','','',NULL,'2026-05-19 07:27:57','2026-05-19 07:27:57');
INSERT INTO `dealer_orders` VALUES (17,'DO202605190646278410',4,'dealer-1779172171086','农副产品加工厂','10086','瑞钧智科','cj','cj','911','FR-1100XS(PRO)(加高)','03-16附加','2026-04-29','heightened',1,0,0,'','','pending','approved','','瑞钧智科','2026-05-19 15:27:57',NULL,'','','',NULL,'2026-05-19 07:27:57','2026-05-19 07:27:57');
INSERT INTO `dealer_orders` VALUES (18,'DO202605190646278410',5,'dealer-1779172171086','农副产品加工厂','10086','瑞钧智科','cj','cj','911','FR-400XS(PRO)','05-02','2026-05-17','wip',4,0,0,'','','pending','approved','','瑞钧智科','2026-05-19 15:27:57',NULL,'','','',NULL,'2026-05-19 07:27:57','2026-05-19 07:27:57');
INSERT INTO `dealer_orders` VALUES (19,'DO202605190638293412',1,'dealer-1779172171086','农副产品加工厂','10086','瑞钧智科','cj','cj','11111','FR-1100XS(PRO)(加高)','03-16附加','2026-04-29','heightened',1,0,0,'','','pending','approved','','瑞钧智科','2026-05-19 15:28:45',NULL,'','','',NULL,'2026-05-19 07:28:45','2026-05-19 07:28:45');
/*!40000 ALTER TABLE `dealer_orders` ENABLE KEYS */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-19 16:34:23



-- MySQL dump 10.13  Distrib 5.7.35, for Linux (x86_64)
--
-- Host: 30.47.14.36    Database: rjfinshed
-- ------------------------------------------------------
-- Server version	5.7.18-cynos-2.1.14-log

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `model_dictionary`
--

/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `model_dictionary` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `model_name` varchar(100) NOT NULL,
  `model_family` varchar(100) DEFAULT '',
  `model_size` varchar(100) DEFAULT NULL,
  `sort_order` int(11) NOT NULL DEFAULT '0',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `remark` varchar(255) DEFAULT '',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_model_dictionary_name` (`model_name`)
) ENGINE=InnoDB AUTO_INCREMENT=293 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `model_dictionary`
--

/*!40000 ALTER TABLE `model_dictionary` DISABLE KEYS */;
INSERT INTO `model_dictionary` VALUES (243,'FR-400G','中小型G',NULL,1,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (244,'FR-500G','中小型G',NULL,4,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (245,'FR-600G','中小型G',NULL,7,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (246,'FR-400XS(PRO)','中小型XS',NULL,2,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (247,'FR-500XS(PRO)','中小型XS',NULL,5,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (248,'FR-600XS(PRO)','中小型XS',NULL,8,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (249,'FR-7055XS(PRO)','中大型XS',NULL,11,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (250,'FR-8055XS(PRO)','中大型XS',NULL,12,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (251,'FR-8060XS(PRO)','中大型XS',NULL,14,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (254,'FR-500AUTO','中小型AUTO',NULL,6,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (255,'FR-600AUTO','中小型AUTO',NULL,9,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (256,'FR-7055AUTO','中大型AUTO',NULL,10,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (257,'FR-8055AUTO','中大型AUTO',NULL,13,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (258,'FR-1100XS(PRO)','特殊',NULL,15,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (259,'FL-1390XS(PRO)','特殊',NULL,16,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (260,'FL-1610XS','特殊',NULL,17,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (261,'FR-1080Y','特殊',NULL,18,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (262,'FR-850MS','特殊',NULL,21,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (264,'FT','特殊',NULL,22,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (265,'FR-1080XS(PRO)','特殊',NULL,23,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (266,'FR-8060AUTO','中大型AUTO',NULL,24,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (268,'FR-8560XS(PRO)','特殊',NULL,19,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (269,'FR-8060Y(PRO)','特殊',NULL,20,1,'','2026-05-09 00:49:01');
INSERT INTO `model_dictionary` VALUES (291,'FH-300C','中小型G',NULL,0,1,'','2026-05-13 20:34:19');
INSERT INTO `model_dictionary` VALUES (292,'FR-400AUTO','中小型AUTO',NULL,3,1,'','2026-05-13 20:34:19');
/*!40000 ALTER TABLE `model_dictionary` ENABLE KEYS */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-19 16:34:23



-- MySQL dump 10.13  Distrib 5.7.35, for Linux (x86_64)
--
-- Host: 30.47.14.36    Database: rjfinshed
-- ------------------------------------------------------
-- Server version	5.7.18-cynos-2.1.14-log

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `wechat_batch_summary`
--

/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `wechat_batch_summary` (
  `summary_id` char(32) NOT NULL,
  `batch_no` varchar(100) NOT NULL,
  `expected_inbound_time` datetime DEFAULT NULL,
  `model` varchar(100) NOT NULL,
  `quantity` int(11) NOT NULL DEFAULT '0',
  `heightened` tinyint(1) NOT NULL DEFAULT '0',
  `original_batch_no` varchar(100) DEFAULT '',
  `original_expected_inbound_time` datetime DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`summary_id`),
  KEY `idx_wechat_batch_summary_batch` (`batch_no`),
  KEY `idx_wechat_batch_summary_inbound` (`expected_inbound_time`),
  KEY `idx_wechat_batch_summary_model` (`model`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `wechat_batch_summary`
--

/*!40000 ALTER TABLE `wechat_batch_summary` DISABLE KEYS */;
INSERT INTO `wechat_batch_summary` VALUES ('094f8a2a08a3be43d2e7f5aad843fe23','加高','2026-04-29 16:00:00','FR-1100XS(PRO)',1,1,'03-16附加','2026-04-29 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('0abba0e0a7a46fe4cf849b4cb947a737','05-02','2026-05-17 16:00:00','FR-400XS(PRO)',17,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('0c2f5c3fd8df04c32669c92d61e3e982','04-13','2026-05-13 16:00:00','FR-400AUTO',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('0f79cb54043e69064d001e8cf3c12728','加高',NULL,'FR-600G',1,1,'07-01',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('0fc5696d72b3ceb558c19104e9194a7a','加高','2026-05-09 16:00:00','FL-8560XS(PRO)',1,1,'03-03附加','2026-05-09 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('14c3fd4e8be0b7430318d2f5dc847a1a','04-19','2026-05-10 16:00:00','FR-600XS(PRO)',4,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('16808894a76ca98d0db0d80a7a843256','04-20','2026-05-12 16:00:00','FR-400G',5,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('17b2e4e2c4641c6761dcf6a80dc8f5b2','加高','2026-06-01 16:00:00','FR-500XS(PRO)',3,1,'05-11','2026-06-01 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('181a0de9b11ea9c3c2ba8fe8b8dd0463','04-09','2026-05-19 16:00:00','FR-8055XS(PRO)',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('1d450b424c3cc8cefbb12d3c4aafe795','04-19附加','2026-05-24 16:00:00','FL-1180XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('1d481925f4ba620206b6fa317f8afefd','04-16','2026-05-17 16:00:00','FR-600AUTO',14,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('1ff7823ca8281c9e647ca8e8fed363ad','04-14','2026-05-15 16:00:00','FR-500AUTO',6,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('23e4e3fcd3d22dea6312626cff36b3e3','05-01','2026-05-24 16:00:00','FR-500AUTO',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('2595f0efd27d45490814bb82e0dc9ad8','库存中','2026-05-24 16:00:00','FR-500XS(PRO)',6,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('259cefcf8397ea4d1c4666b0148c3e5b','01-03',NULL,'FR-7055XS(PRO)',2,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('25d1fdd9e2dea4dccf9b3de22cb1564c','05-12','2026-06-16 16:00:00','FR-8055AUTO',4,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('261026134925f0ad0a749bd9b37a691d','05-07','2026-05-28 16:00:00','FR-400AUTO',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('2770949f453a410b81bceecbde6fbffd','05-09','2026-05-29 16:00:00','FR-400G',25,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('280621ab5644801148a8089acff2ea1d','加高','2026-03-15 16:00:00','FR-8060XS(PRO)',1,1,'02-03附加','2026-03-15 16:00:00','2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('286fb2d78478a58f99901e3f36669fc4','加高','2026-05-17 16:00:00','FR-600XS(PRO)',1,1,'05-02','2026-05-17 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('2b3ec2f39b023bd6f261aa220b4d4413','05-16','2026-06-08 16:00:00','FH-300C',1,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('2e11f6d712fb8b982cc3b55f9dc9431c','加高',NULL,'FR-1080Y',1,1,'库存中',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('2e32d001d58dcb323891a723576c166e','04-01','2026-04-20 16:00:00','FR-600G',1,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('2e81424be3ca52ed08d46e63b6dbc01a','04-14','2026-05-15 16:00:00','FR-400AUTO',9,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('30620f807cf1c7ee99b3a31c7ce3280a','05-09','2026-05-29 16:00:00','FR-500G',5,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('35cfd2466ce45302a329548cdf9adb8c','04-19','2026-05-10 16:00:00','FR-400XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('3626fb58b89fc7cb9672bf05516e98ec','库存中',NULL,'FR-400XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('3715f39c13b7dee89d1be23e494be53c','05-05附加','2026-06-29 16:00:00','FR-8060Y',1,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('383971804a48005ced53a1e8d6f101dd','04-19','2026-05-10 16:00:00','FR-500XS(PRO)',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('3a13bc297ed30f82658e9777dff38279','04-10','2026-05-29 16:00:00','FR-7055AUTO',8,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('3b583460770c401fa0528181d9f9b468','05-02','2026-05-17 16:00:00','FR-600XS(PRO)',4,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('401f44ec86522fae99251b64ee955d9f','04-14','2026-05-15 16:00:00','FR-600AUTO',8,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('4424f75ead25a1fdf640d00436380f3e','01-03',NULL,'FR-8055XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('4439af68e5fca7145363f03ebb0e1c12','05-08','2026-05-27 16:00:00','FR-400XS(PRO)',18,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('46315a6e641f83174e14815bf99d5a98','04-18','2026-05-20 16:00:00','FR-500AUTO',6,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('4ad3f2059efd7e06859abdb47494ca79','库存中','2026-05-24 16:00:00','FR-8060XS(PRO)',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('4d03c5a63bcf577360f0b731a47f10e1','05-01','2026-05-24 16:00:00','FR-600AUTO',7,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('50de0451d9dfe6afdada927040d4c5e7','加高','2026-05-19 16:00:00','FR-8055XS(PRO)',1,1,'04-09','2026-05-19 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('514fbcdfd764c8e3a7c859823775e57a','04-10','2026-05-29 16:00:00','FR-8055AUTO',5,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('57a19cb08cbfa93a21c3088a63e4b76f','库存中',NULL,'FR-1100XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('57d1af347f58056624eec966e4c4b2e5','05-01','2026-05-24 16:00:00','FR-400AUTO',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('5824d6b7aad7daad3929ea3918b5d646','加高','2026-04-15 16:00:00','FR-400XS(PRO)',1,1,'03-13','2026-04-15 16:00:00','2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('5a79ca42e57cdb06593952a72519b47a','库存中','2026-05-11 16:00:00','FR-500AUTO',1,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('5c7331326eb247fb2ee588b6ad874477','05-07','2026-05-28 16:00:00','FR-600AUTO',7,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('604028f1fb7cfdd234e7fdc6bfcfb141','05-11','2026-06-01 16:00:00','FR-400XS(PRO)',20,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('64712b39509546f047c011a23c8591b6','03-04','2026-04-29 16:00:00','FR-8055AUTO',6,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('64f38c87769d4199fe040f503d5387b6','库存中','2026-05-07 16:00:00','FR-600XS(PRO)',3,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('67d2e84a2c67bd101fba0a3345e10d46','04-03','2026-05-09 16:00:00','FR-7055XS(PRO)',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('6b4ca930c7f4ce90d5f9e66807479360','04-16','2026-05-17 16:00:00','FR-500AUTO',8,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('6ff5193c524e8a34627c67e25c419dad','加高','2026-06-09 16:00:00','FL-1610XS',1,1,'04-06附加','2026-06-09 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('70cce73553f2247edcd3651d87cf9d9b','05-02','2026-05-17 16:00:00','FR-500XS(PRO)',7,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('71661ad40fb5bc3ce0ce72b23eb97137','04-09','2026-05-19 16:00:00','FR-7055XS(PRO)',12,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('738e27863ccf8feec24da43ad2925656','11-14',NULL,'FR-1080XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('74c1b524ef6bd5ff99167d4330f665e1','库存中','2026-05-26 16:00:00','FR-600AUTO',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('7d08756cc6c4222f71969135047c25b2','库存中','2026-05-26 16:00:00','FR-500AUTO',8,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('7e600ea6aa995d563e041d6bbe59b91e','加高','2026-05-24 16:00:00','FR-8060Y',2,1,'04-19附加','2026-05-24 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('7fcae2e7557f061bcdd1c08487becbd7','05-12','2026-06-16 16:00:00','FR-7055AUTO',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('7fe3ede60040dc3ca81415bbbf12e841','04-01','2026-04-20 16:00:00','FR-400G',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('82e532005e1f8e496e0f8d5b97944931','04-19附加','2026-05-24 16:00:00','FR-1100XS(PRO)',3,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('84aad8b4e4a2d560eb540247b17de774','05-08','2026-05-27 16:00:00','FR-600XS(PRO)',6,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('866d33fb1176298eba438cb5faac03dc','04-16','2026-05-17 16:00:00','FR-400AUTO',5,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('86d2de6fb468a93e4075229bcc60883f','05-11','2026-06-01 16:00:00','FR-500XS(PRO)',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('8d4ecc348f37e0d0018cde93d53cb3f7','库存中',NULL,'FR-1080Y',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('94e192e2f3b4d71589155b066c496775','05-05','2026-05-22 16:00:00','FR-600XS(PRO)',3,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('968d4f387398f70f3ac3095cdf4f9dc3','04-20','2026-05-12 16:00:00','FH-300C',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('98dbd8e956048e39979f493183247dd7','11-05',NULL,'FT',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('99a7f5d2c73c844d76270a231eb31c0b','04-13','2026-05-13 16:00:00','FR-500AUTO',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('a018b1c98a005db9f40b2b25bac1518d','加高',NULL,'FR-600G',1,1,'库存中',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('a08f9eebf2de1dadfcb207b830c8ab0c','03-13','2026-04-15 16:00:00','FT',2,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('a13eb3fe4e29cb7f11b86a61f3f00653','05-08','2026-05-27 16:00:00','FR-500XS(PRO)',6,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('a609185a189767aab61efed140535894','05-03','2026-05-19 16:00:00','FR-400G',24,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('a77702091a22b33ff9652b1ca9fcf12b','库存中','2026-05-24 16:00:00','FR-400XS(PRO)',18,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('abc2456328d462eb3d511b14e64d3942','04-18','2026-05-20 16:00:00','FR-400AUTO',13,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('ac8e5066ef11e7d83f948408d38d8f00','加高','2026-04-24 16:00:00','FR-400XS(PRO)',2,1,'03-18','2026-04-24 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('b270232035c43513c999073d2d03e3d6','04-18','2026-05-20 16:00:00','FR-600AUTO',8,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('b3c7bb0ee115c49b725c1162b52e3413','04-10','2026-05-29 16:00:00','FR-8060AUTO',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('b3ec001be56d918d51a21f52322d6270','03-13','2026-04-15 16:00:00','FR-600XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('b4bf3e43ab85a4ee365b0a1b1941b719','加高','2026-04-27 16:00:00','FR-600XS(PRO)',1,1,'04-07','2026-04-27 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('b868a69729cf2082ffe9efdd3eacba06','05-05','2026-05-22 16:00:00','FR-400XS(PRO)',17,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('bfc4115bd27734240d1db0da59b6f61f','库存中',NULL,'FR-400XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('bffe1b000e90869803b2f02e692ae088','加高','2026-05-24 16:00:00','FR-7055XS(PRO)',3,1,'04-21','2026-05-24 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('c0b4c7eb25b959b0c478ee2153a2f459','库存中','2026-05-24 16:00:00','FR-7055XS(PRO)',7,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('c567000632ad83362960fdff86035ca3','库存中',NULL,'FR-400AUTO',6,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('c5f966d25552ce0d3515ffb13bcd2952','加高','2026-05-24 16:00:00','FL-1180XS(PRO)',1,1,'04-19附加','2026-05-24 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('c6574484bd876f21aaa2335c7115c478','05-03','2026-05-19 16:00:00','FR-500G',1,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('c6e8f883804f95c1529ca0d31a58e90a','05-07','2026-05-28 16:00:00','FR-500AUTO',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('c8f7277668094c6f9c44f4fc68039e0f','加高','2026-05-17 16:00:00','FR-500XS(PRO)',1,1,'05-02','2026-05-17 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('ca266a6b04319f7a604248e79d737990','加高',NULL,'FL-1610XS',1,1,'库存中',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('cc5cd85dadc70542a5eb618e54016bff','04-13','2026-05-13 16:00:00','FR-600AUTO',6,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('d0da20341ad5b3e6c5f37c618b7145b9','库存中',NULL,'FR-400XS(PRO)',2,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('d7720495ab97d53f8540d0a4623f2d1d','库存中',NULL,'FR-8055XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('d9c6a0942d40fac1645aea995e22b35c','加高','2026-05-19 16:00:00','FR-7055XS(PRO)',1,1,'04-09','2026-05-19 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('da96b3b4edad3f357ab97fd779401f69','05-03','2026-05-19 16:00:00','FH-300C',4,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('db236788e984077b46d9897c301d6b75','库存中','2026-05-26 16:00:00','FR-400AUTO',9,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('dcd5ff9e6734554f352bc7f42c95230f','04-22','2026-06-04 16:00:00','FR-7055AUTO',15,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('de5974124ee5bd399b67401922fac138','05-10','2026-05-31 16:00:00','FR-600AUTO',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('e0d430f2a059342dfe90b0feaecc95bd','05-11','2026-06-01 16:00:00','FR-600XS(PRO)',5,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('e169ca697154090328425003178a8a68','05-05','2026-05-22 16:00:00','FR-500XS(PRO)',10,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('e850d6044c307ff3d0da69cbc7a65b36','05-16','2026-06-08 16:00:00','FR-600G',7,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('e9cfa8304fba372b0275d6968a171280','库存中','2026-05-24 16:00:00','FR-600XS(PRO)',5,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('ea1f206af8202d0ca4b22a0185cc96c3','05-10','2026-05-31 16:00:00','FR-400AUTO',17,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('eec4e37450489759b293a683008d7522','加高','2026-05-24 16:00:00','FR-8055XS(PRO)',1,1,'04-21','2026-05-24 16:00:00','2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('efe202745a5ad79b448e4af39a51b570','库存中','2026-05-24 16:00:00','FR-8055XS(PRO)',3,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('f45b582e9cc21472fbf33d59ba85a4c4','库存中',NULL,'FR-500XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('f4b50dc5cea77aefe5c87ac58061afea','04-03','2026-05-09 16:00:00','FR-8055XS(PRO)',2,0,'',NULL,'2026-05-17 21:19:30');
INSERT INTO `wechat_batch_summary` VALUES ('f526db7130971fddf6cffd478b5e543b','11-14',NULL,'FL-1390XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('f6b7d56e5208b6d305c0e0eecd34331c','库存中',NULL,'FL-1390XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('f918cab236479f7e16e78ce03f1a5d39','库存中',NULL,'FR-600XS(PRO)',1,0,'',NULL,'2026-05-17 21:19:29');
INSERT INTO `wechat_batch_summary` VALUES ('fff38d1135c05e3c4fd3eca4ac9c3eec','07-09',NULL,'FR-850MS',1,0,'',NULL,'2026-05-17 21:19:29');
/*!40000 ALTER TABLE `wechat_batch_summary` ENABLE KEYS */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-19 16:34:24



