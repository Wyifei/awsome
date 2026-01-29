package com.authplatform.userservice.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 客户端信息 DTO
 * 用于追踪用户来源渠道和设备信息
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ClientInfo {

    /**
     * 触点渠道
     * website - 官网
     * wechat - 微信公众号/小程序
     * app_ios - iOS App
     * app_android - Android App
     * admin - 管理后台
     */
    private String channel;

    /**
     * 设备类型
     * desktop - 桌面端
     * mobile - 移动端
     * tablet - 平板
     */
    private String device;

    /**
     * 操作系统/平台
     * windows, macos, linux, ios, android
     */
    private String platform;

    /**
     * 应用版本号 (App 场景)
     */
    private String appVersion;

    // 渠道常量
    public static final String CHANNEL_WEBSITE = "website";
    public static final String CHANNEL_WECHAT = "wechat";
    public static final String CHANNEL_APP_IOS = "app_ios";
    public static final String CHANNEL_APP_ANDROID = "app_android";
    public static final String CHANNEL_ADMIN = "admin";
    public static final String CHANNEL_UNKNOWN = "unknown";

    // 设备常量
    public static final String DEVICE_DESKTOP = "desktop";
    public static final String DEVICE_MOBILE = "mobile";
    public static final String DEVICE_TABLET = "tablet";
    public static final String DEVICE_UNKNOWN = "unknown";

    // 平台常量
    public static final String PLATFORM_WINDOWS = "windows";
    public static final String PLATFORM_MACOS = "macos";
    public static final String PLATFORM_LINUX = "linux";
    public static final String PLATFORM_IOS = "ios";
    public static final String PLATFORM_ANDROID = "android";
    public static final String PLATFORM_UNKNOWN = "unknown";

    /**
     * 获取安全的 channel 值（用于 metrics 标签）
     */
    public String getSafeChannel() {
        if (channel == null || channel.isBlank()) {
            return CHANNEL_UNKNOWN;
        }
        return switch (channel.toLowerCase()) {
            case "website", "web" -> CHANNEL_WEBSITE;
            case "wechat", "weixin", "wx" -> CHANNEL_WECHAT;
            case "app_ios", "ios" -> CHANNEL_APP_IOS;
            case "app_android", "android" -> CHANNEL_APP_ANDROID;
            case "admin", "backend" -> CHANNEL_ADMIN;
            default -> CHANNEL_UNKNOWN;
        };
    }

    /**
     * 获取安全的 device 值（用于 metrics 标签）
     */
    public String getSafeDevice() {
        if (device == null || device.isBlank()) {
            return DEVICE_UNKNOWN;
        }
        return switch (device.toLowerCase()) {
            case "desktop", "pc" -> DEVICE_DESKTOP;
            case "mobile", "phone" -> DEVICE_MOBILE;
            case "tablet", "pad" -> DEVICE_TABLET;
            default -> DEVICE_UNKNOWN;
        };
    }

    /**
     * 获取安全的 platform 值（用于 metrics 标签）
     */
    public String getSafePlatform() {
        if (platform == null || platform.isBlank()) {
            return PLATFORM_UNKNOWN;
        }
        return switch (platform.toLowerCase()) {
            case "windows", "win" -> PLATFORM_WINDOWS;
            case "macos", "mac", "osx" -> PLATFORM_MACOS;
            case "linux" -> PLATFORM_LINUX;
            case "ios", "iphone", "ipad" -> PLATFORM_IOS;
            case "android" -> PLATFORM_ANDROID;
            default -> PLATFORM_UNKNOWN;
        };
    }

    /**
     * 创建默认的未知客户端信息
     */
    public static ClientInfo unknown() {
        return ClientInfo.builder()
                .channel(CHANNEL_UNKNOWN)
                .device(DEVICE_UNKNOWN)
                .platform(PLATFORM_UNKNOWN)
                .build();
    }
}
