-- WeChat cloud database import, ASCII column version
-- Requires existing database: rjfinshed
USE `rjfinshed`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

DROP TABLE IF EXISTS `wechat_batch_summary`;
CREATE TABLE `wechat_batch_summary` (
  `summary_id` char(32) NOT NULL,
  `batch_no` varchar(100) NOT NULL,
  `expected_inbound_time` datetime DEFAULT NULL,
  `model` varchar(100) NOT NULL,
  `quantity` int NOT NULL DEFAULT 0,
  `heightened` tinyint(1) NOT NULL DEFAULT 0,
  `original_batch_no` varchar(100) DEFAULT '',
  `original_expected_inbound_time` datetime DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`summary_id`),
  KEY `idx_wechat_batch_summary_batch` (`batch_no`),
  KEY `idx_wechat_batch_summary_inbound` (`expected_inbound_time`),
  KEY `idx_wechat_batch_summary_model` (`model`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('259cefcf8397ea4d1c4666b0148c3e5b', '01-03', NULL, 'FR-7055XS(PRO)', 2, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('4424f75ead25a1fdf640d00436380f3e', '01-03', NULL, 'FR-8055XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('fff38d1135c05e3c4fd3eca4ac9c3eec', '07-09', NULL, 'FR-850MS', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('98dbd8e956048e39979f493183247dd7', '11-05', NULL, 'FT', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('f526db7130971fddf6cffd478b5e543b', '11-14', NULL, 'FL-1390XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('738e27863ccf8feec24da43ad2925656', '11-14', NULL, 'FR-1080XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('ca266a6b04319f7a604248e79d737990', '加高', NULL, 'FL-1610XS', 1, 1, '库存中', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('2e11f6d712fb8b982cc3b55f9dc9431c', '加高', NULL, 'FR-1080Y', 1, 1, '库存中', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('a018b1c98a005db9f40b2b25bac1518d', '加高', NULL, 'FR-600G', 1, 1, '库存中', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('0f79cb54043e69064d001e8cf3c12728', '加高', NULL, 'FR-600G', 1, 1, '07-01', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('f6b7d56e5208b6d305c0e0eecd34331c', '库存中', NULL, 'FL-1390XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('8d4ecc348f37e0d0018cde93d53cb3f7', '库存中', NULL, 'FR-1080Y', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('57a19cb08cbfa93a21c3088a63e4b76f', '库存中', NULL, 'FR-1100XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('c567000632ad83362960fdff86035ca3', '库存中', NULL, 'FR-400AUTO', 6, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('3626fb58b89fc7cb9672bf05516e98ec', '库存中', NULL, 'FR-400XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('d0da20341ad5b3e6c5f37c618b7145b9', '库存中', NULL, 'FR-400XS(PRO)', 2, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('bfc4115bd27734240d1db0da59b6f61f', '库存中', NULL, 'FR-400XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('f45b582e9cc21472fbf33d59ba85a4c4', '库存中', NULL, 'FR-500XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('f918cab236479f7e16e78ce03f1a5d39', '库存中', NULL, 'FR-600XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('d7720495ab97d53f8540d0a4623f2d1d', '库存中', NULL, 'FR-8055XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('280621ab5644801148a8089acff2ea1d', '加高', '2026-03-15 16:00:00', 'FR-8060XS(PRO)', 1, 1, '02-03附加', '2026-03-15 16:00:00', '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('b3ec001be56d918d51a21f52322d6270', '03-13', '2026-04-15 16:00:00', 'FR-600XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('a08f9eebf2de1dadfcb207b830c8ab0c', '03-13', '2026-04-15 16:00:00', 'FT', 2, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('5824d6b7aad7daad3929ea3918b5d646', '加高', '2026-04-15 16:00:00', 'FR-400XS(PRO)', 1, 1, '03-13', '2026-04-15 16:00:00', '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('7fe3ede60040dc3ca81415bbbf12e841', '04-01', '2026-04-20 16:00:00', 'FR-400G', 1, 0, '', NULL, '2026-05-18 05:19:29');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('2e32d001d58dcb323891a723576c166e', '04-01', '2026-04-20 16:00:00', 'FR-600G', 1, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('ac8e5066ef11e7d83f948408d38d8f00', '加高', '2026-04-24 16:00:00', 'FR-400XS(PRO)', 2, 1, '03-18', '2026-04-24 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('b4bf3e43ab85a4ee365b0a1b1941b719', '加高', '2026-04-27 16:00:00', 'FR-600XS(PRO)', 1, 1, '04-07', '2026-04-27 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('64712b39509546f047c011a23c8591b6', '03-04', '2026-04-29 16:00:00', 'FR-8055AUTO', 6, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('094f8a2a08a3be43d2e7f5aad843fe23', '加高', '2026-04-29 16:00:00', 'FR-1100XS(PRO)', 1, 1, '03-16附加', '2026-04-29 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('64f38c87769d4199fe040f503d5387b6', '库存中', '2026-05-07 16:00:00', 'FR-600XS(PRO)', 3, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('67d2e84a2c67bd101fba0a3345e10d46', '04-03', '2026-05-09 16:00:00', 'FR-7055XS(PRO)', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('f4b50dc5cea77aefe5c87ac58061afea', '04-03', '2026-05-09 16:00:00', 'FR-8055XS(PRO)', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('0fc5696d72b3ceb558c19104e9194a7a', '加高', '2026-05-09 16:00:00', 'FL-8560XS(PRO)', 1, 1, '03-03附加', '2026-05-09 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('35cfd2466ce45302a329548cdf9adb8c', '04-19', '2026-05-10 16:00:00', 'FR-400XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('383971804a48005ced53a1e8d6f101dd', '04-19', '2026-05-10 16:00:00', 'FR-500XS(PRO)', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('14c3fd4e8be0b7430318d2f5dc847a1a', '04-19', '2026-05-10 16:00:00', 'FR-600XS(PRO)', 4, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('5a79ca42e57cdb06593952a72519b47a', '库存中', '2026-05-11 16:00:00', 'FR-500AUTO', 1, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('968d4f387398f70f3ac3095cdf4f9dc3', '04-20', '2026-05-12 16:00:00', 'FH-300C', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('16808894a76ca98d0db0d80a7a843256', '04-20', '2026-05-12 16:00:00', 'FR-400G', 5, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('0c2f5c3fd8df04c32669c92d61e3e982', '04-13', '2026-05-13 16:00:00', 'FR-400AUTO', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('99a7f5d2c73c844d76270a231eb31c0b', '04-13', '2026-05-13 16:00:00', 'FR-500AUTO', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('cc5cd85dadc70542a5eb618e54016bff', '04-13', '2026-05-13 16:00:00', 'FR-600AUTO', 6, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('2e81424be3ca52ed08d46e63b6dbc01a', '04-14', '2026-05-15 16:00:00', 'FR-400AUTO', 9, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('1ff7823ca8281c9e647ca8e8fed363ad', '04-14', '2026-05-15 16:00:00', 'FR-500AUTO', 6, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('401f44ec86522fae99251b64ee955d9f', '04-14', '2026-05-15 16:00:00', 'FR-600AUTO', 8, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('866d33fb1176298eba438cb5faac03dc', '04-16', '2026-05-17 16:00:00', 'FR-400AUTO', 5, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('6b4ca930c7f4ce90d5f9e66807479360', '04-16', '2026-05-17 16:00:00', 'FR-500AUTO', 8, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('1d481925f4ba620206b6fa317f8afefd', '04-16', '2026-05-17 16:00:00', 'FR-600AUTO', 14, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('0abba0e0a7a46fe4cf849b4cb947a737', '05-02', '2026-05-17 16:00:00', 'FR-400XS(PRO)', 17, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('70cce73553f2247edcd3651d87cf9d9b', '05-02', '2026-05-17 16:00:00', 'FR-500XS(PRO)', 7, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('3b583460770c401fa0528181d9f9b468', '05-02', '2026-05-17 16:00:00', 'FR-600XS(PRO)', 4, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('c8f7277668094c6f9c44f4fc68039e0f', '加高', '2026-05-17 16:00:00', 'FR-500XS(PRO)', 1, 1, '05-02', '2026-05-17 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('286fb2d78478a58f99901e3f36669fc4', '加高', '2026-05-17 16:00:00', 'FR-600XS(PRO)', 1, 1, '05-02', '2026-05-17 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('71661ad40fb5bc3ce0ce72b23eb97137', '04-09', '2026-05-19 16:00:00', 'FR-7055XS(PRO)', 12, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('181a0de9b11ea9c3c2ba8fe8b8dd0463', '04-09', '2026-05-19 16:00:00', 'FR-8055XS(PRO)', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('da96b3b4edad3f357ab97fd779401f69', '05-03', '2026-05-19 16:00:00', 'FH-300C', 4, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('a609185a189767aab61efed140535894', '05-03', '2026-05-19 16:00:00', 'FR-400G', 24, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('c6574484bd876f21aaa2335c7115c478', '05-03', '2026-05-19 16:00:00', 'FR-500G', 1, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('d9c6a0942d40fac1645aea995e22b35c', '加高', '2026-05-19 16:00:00', 'FR-7055XS(PRO)', 1, 1, '04-09', '2026-05-19 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('50de0451d9dfe6afdada927040d4c5e7', '加高', '2026-05-19 16:00:00', 'FR-8055XS(PRO)', 1, 1, '04-09', '2026-05-19 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('abc2456328d462eb3d511b14e64d3942', '04-18', '2026-05-20 16:00:00', 'FR-400AUTO', 13, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('46315a6e641f83174e14815bf99d5a98', '04-18', '2026-05-20 16:00:00', 'FR-500AUTO', 6, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('b270232035c43513c999073d2d03e3d6', '04-18', '2026-05-20 16:00:00', 'FR-600AUTO', 8, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('b868a69729cf2082ffe9efdd3eacba06', '05-05', '2026-05-22 16:00:00', 'FR-400XS(PRO)', 17, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('e169ca697154090328425003178a8a68', '05-05', '2026-05-22 16:00:00', 'FR-500XS(PRO)', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('94e192e2f3b4d71589155b066c496775', '05-05', '2026-05-22 16:00:00', 'FR-600XS(PRO)', 3, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('1d450b424c3cc8cefbb12d3c4aafe795', '04-19附加', '2026-05-24 16:00:00', 'FL-1180XS(PRO)', 1, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('82e532005e1f8e496e0f8d5b97944931', '04-19附加', '2026-05-24 16:00:00', 'FR-1100XS(PRO)', 3, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('57d1af347f58056624eec966e4c4b2e5', '05-01', '2026-05-24 16:00:00', 'FR-400AUTO', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('23e4e3fcd3d22dea6312626cff36b3e3', '05-01', '2026-05-24 16:00:00', 'FR-500AUTO', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('4d03c5a63bcf577360f0b731a47f10e1', '05-01', '2026-05-24 16:00:00', 'FR-600AUTO', 7, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('c5f966d25552ce0d3515ffb13bcd2952', '加高', '2026-05-24 16:00:00', 'FL-1180XS(PRO)', 1, 1, '04-19附加', '2026-05-24 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('bffe1b000e90869803b2f02e692ae088', '加高', '2026-05-24 16:00:00', 'FR-7055XS(PRO)', 3, 1, '04-21', '2026-05-24 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('eec4e37450489759b293a683008d7522', '加高', '2026-05-24 16:00:00', 'FR-8055XS(PRO)', 1, 1, '04-21', '2026-05-24 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('7e600ea6aa995d563e041d6bbe59b91e', '加高', '2026-05-24 16:00:00', 'FR-8060Y', 2, 1, '04-19附加', '2026-05-24 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('a77702091a22b33ff9652b1ca9fcf12b', '库存中', '2026-05-24 16:00:00', 'FR-400XS(PRO)', 18, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('2595f0efd27d45490814bb82e0dc9ad8', '库存中', '2026-05-24 16:00:00', 'FR-500XS(PRO)', 6, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('e9cfa8304fba372b0275d6968a171280', '库存中', '2026-05-24 16:00:00', 'FR-600XS(PRO)', 5, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('c0b4c7eb25b959b0c478ee2153a2f459', '库存中', '2026-05-24 16:00:00', 'FR-7055XS(PRO)', 7, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('efe202745a5ad79b448e4af39a51b570', '库存中', '2026-05-24 16:00:00', 'FR-8055XS(PRO)', 3, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('4ad3f2059efd7e06859abdb47494ca79', '库存中', '2026-05-24 16:00:00', 'FR-8060XS(PRO)', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('db236788e984077b46d9897c301d6b75', '库存中', '2026-05-26 16:00:00', 'FR-400AUTO', 9, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('7d08756cc6c4222f71969135047c25b2', '库存中', '2026-05-26 16:00:00', 'FR-500AUTO', 8, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('74c1b524ef6bd5ff99167d4330f665e1', '库存中', '2026-05-26 16:00:00', 'FR-600AUTO', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('4439af68e5fca7145363f03ebb0e1c12', '05-08', '2026-05-27 16:00:00', 'FR-400XS(PRO)', 18, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('a13eb3fe4e29cb7f11b86a61f3f00653', '05-08', '2026-05-27 16:00:00', 'FR-500XS(PRO)', 6, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('84aad8b4e4a2d560eb540247b17de774', '05-08', '2026-05-27 16:00:00', 'FR-600XS(PRO)', 6, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('261026134925f0ad0a749bd9b37a691d', '05-07', '2026-05-28 16:00:00', 'FR-400AUTO', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('c6e8f883804f95c1529ca0d31a58e90a', '05-07', '2026-05-28 16:00:00', 'FR-500AUTO', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('5c7331326eb247fb2ee588b6ad874477', '05-07', '2026-05-28 16:00:00', 'FR-600AUTO', 7, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('3a13bc297ed30f82658e9777dff38279', '04-10', '2026-05-29 16:00:00', 'FR-7055AUTO', 8, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('514fbcdfd764c8e3a7c859823775e57a', '04-10', '2026-05-29 16:00:00', 'FR-8055AUTO', 5, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('b3c7bb0ee115c49b725c1162b52e3413', '04-10', '2026-05-29 16:00:00', 'FR-8060AUTO', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('2770949f453a410b81bceecbde6fbffd', '05-09', '2026-05-29 16:00:00', 'FR-400G', 25, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('30620f807cf1c7ee99b3a31c7ce3280a', '05-09', '2026-05-29 16:00:00', 'FR-500G', 5, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('ea1f206af8202d0ca4b22a0185cc96c3', '05-10', '2026-05-31 16:00:00', 'FR-400AUTO', 17, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('de5974124ee5bd399b67401922fac138', '05-10', '2026-05-31 16:00:00', 'FR-600AUTO', 10, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('604028f1fb7cfdd234e7fdc6bfcfb141', '05-11', '2026-06-01 16:00:00', 'FR-400XS(PRO)', 20, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('86d2de6fb468a93e4075229bcc60883f', '05-11', '2026-06-01 16:00:00', 'FR-500XS(PRO)', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('e0d430f2a059342dfe90b0feaecc95bd', '05-11', '2026-06-01 16:00:00', 'FR-600XS(PRO)', 5, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('17b2e4e2c4641c6761dcf6a80dc8f5b2', '加高', '2026-06-01 16:00:00', 'FR-500XS(PRO)', 3, 1, '05-11', '2026-06-01 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('dcd5ff9e6734554f352bc7f42c95230f', '04-22', '2026-06-04 16:00:00', 'FR-7055AUTO', 15, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('2b3ec2f39b023bd6f261aa220b4d4413', '05-16', '2026-06-08 16:00:00', 'FH-300C', 1, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('e850d6044c307ff3d0da69cbc7a65b36', '05-16', '2026-06-08 16:00:00', 'FR-600G', 7, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('6ff5193c524e8a34627c67e25c419dad', '加高', '2026-06-09 16:00:00', 'FL-1610XS', 1, 1, '04-06附加', '2026-06-09 16:00:00', '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('7fcae2e7557f061bcdd1c08487becbd7', '05-12', '2026-06-16 16:00:00', 'FR-7055AUTO', 2, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('25d1fdd9e2dea4dccf9b3de22cb1564c', '05-12', '2026-06-16 16:00:00', 'FR-8055AUTO', 4, 0, '', NULL, '2026-05-18 05:19:30');
INSERT INTO `wechat_batch_summary` (`summary_id`, `batch_no`, `expected_inbound_time`, `model`, `quantity`, `heightened`, `original_batch_no`, `original_expected_inbound_time`, `updated_at`) VALUES ('3715f39c13b7dee89d1be23e494be53c', '05-05附加', '2026-06-29 16:00:00', 'FR-8060Y', 1, 0, '', NULL, '2026-05-18 05:19:30');

DROP TABLE IF EXISTS `dealer_applications`;
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
DROP TABLE IF EXISTS `dealer_orders`;
CREATE TABLE `dealer_orders` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `order_no` varchar(64) NOT NULL,
  `line_no` int NOT NULL DEFAULT 1,
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
  `quantity` int NOT NULL DEFAULT 1,
  `approved_qty` int NOT NULL DEFAULT 0,
  `allocated_qty` int NOT NULL DEFAULT 0,
  `delivery_date` varchar(64) DEFAULT '',
  `remark` text,
  `status` varchar(32) NOT NULL DEFAULT 'pending',
  `reviewed_at` datetime DEFAULT NULL,
  `reviewed_by` varchar(128) DEFAULT '',
  `contract_no` varchar(128) DEFAULT '',
  `v7_order_no` varchar(128) DEFAULT '',
  `review_note` text,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_dealer_order_line` (`order_no`, `line_no`),
  KEY `idx_dealer_order_no` (`order_no`),
  KEY `idx_dealer_id` (`dealer_id`),
  KEY `idx_status` (`status`),
  KEY `idx_batch_model_status` (`batch_no`, `model`, `status`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
DROP TABLE IF EXISTS `model_dictionary`;
CREATE TABLE `model_dictionary` (
  `id` int NOT NULL AUTO_INCREMENT,
  `model_name` varchar(100) NOT NULL,
  `model_family` varchar(100) DEFAULT '',
  `model_size` varchar(100) DEFAULT NULL,
  `sort_order` int NOT NULL DEFAULT 0,
  `enabled` tinyint(1) NOT NULL DEFAULT 1,
  `remark` varchar(255) DEFAULT '',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_model_dictionary_name` (`model_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (291, 'FH-300C', '中小型G', NULL, 0, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (243, 'FR-400G', '中小型G', NULL, 1, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (246, 'FR-400XS(PRO)', '中小型XS', NULL, 2, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (292, 'FR-400AUTO', '中小型AUTO', NULL, 3, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (244, 'FR-500G', '中小型G', NULL, 4, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (247, 'FR-500XS(PRO)', '中小型XS', NULL, 5, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (254, 'FR-500AUTO', '中小型AUTO', NULL, 6, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (245, 'FR-600G', '中小型G', NULL, 7, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (248, 'FR-600XS(PRO)', '中小型XS', NULL, 8, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (255, 'FR-600AUTO', '中小型AUTO', NULL, 9, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (256, 'FR-7055AUTO', '中大型AUTO', NULL, 10, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (249, 'FR-7055XS(PRO)', '中大型XS', NULL, 11, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (250, 'FR-8055XS(PRO)', '中大型XS', NULL, 12, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (257, 'FR-8055AUTO', '中大型AUTO', NULL, 13, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (251, 'FR-8060XS(PRO)', '中大型XS', NULL, 14, 1, '', '2026-05-14 04:34:19');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (258, 'FR-1100XS(PRO)', '特殊', NULL, 15, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (259, 'FL-1390XS(PRO)', '特殊', NULL, 16, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (260, 'FL-1610XS', '特殊', NULL, 17, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (261, 'FR-1080Y', '特殊', NULL, 18, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (268, 'FR-8560XS(PRO)', '特殊', NULL, 19, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (269, 'FR-8060Y(PRO)', '特殊', NULL, 20, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (262, 'FR-850MS', '特殊', NULL, 21, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (264, 'FT', '特殊', NULL, 22, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (265, 'FR-1080XS(PRO)', '特殊', NULL, 23, 1, '', '2026-05-09 08:49:01');
INSERT INTO `model_dictionary` (`id`, `model_name`, `model_family`, `model_size`, `sort_order`, `enabled`, `remark`, `updated_at`) VALUES (266, 'FR-8060AUTO', '中大型AUTO', NULL, 24, 1, '', '2026-05-14 04:34:19');

SET FOREIGN_KEY_CHECKS=1;
