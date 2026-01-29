package com.authplatform.userservice.metrics;

import com.authplatform.userservice.dto.ClientInfo;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/**
 * 客户端信息解析器
 * 从 HTTP 请求头中提取客户端信息
 *
 * 支持的请求头:
 * - X-Client-Channel: website | wechat | app_ios | app_android | admin
 * - X-Client-Device: desktop | mobile | tablet
 * - X-Client-Platform: windows | macos | linux | ios | android
 * - X-App-Version: 应用版本号
 *
 * 也支持从 User-Agent 自动推断设备和平台信息
 */
@Component
@Slf4j
public class ClientInfoResolver {

    // 请求头名称
    public static final String HEADER_CHANNEL = "X-Client-Channel";
    public static final String HEADER_DEVICE = "X-Client-Device";
    public static final String HEADER_PLATFORM = "X-Client-Platform";
    public static final String HEADER_APP_VERSION = "X-App-Version";

    /**
     * 从当前请求上下文解析客户端信息
     */
    public ClientInfo resolve() {
        ServletRequestAttributes attrs = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attrs == null) {
            return ClientInfo.unknown();
        }
        return resolve(attrs.getRequest());
    }

    /**
     * 从 HTTP 请求解析客户端信息
     */
    public ClientInfo resolve(HttpServletRequest request) {
        if (request == null) {
            return ClientInfo.unknown();
        }

        // 优先从自定义 Header 获取
        String channel = request.getHeader(HEADER_CHANNEL);
        String device = request.getHeader(HEADER_DEVICE);
        String platform = request.getHeader(HEADER_PLATFORM);
        String appVersion = request.getHeader(HEADER_APP_VERSION);

        // 如果没有自定义 Header，尝试从 User-Agent 推断
        String userAgent = request.getHeader("User-Agent");
        if (userAgent != null && !userAgent.isBlank()) {
            if (device == null || device.isBlank()) {
                device = inferDeviceFromUserAgent(userAgent);
            }
            if (platform == null || platform.isBlank()) {
                platform = inferPlatformFromUserAgent(userAgent);
            }
            if (channel == null || channel.isBlank()) {
                channel = inferChannelFromUserAgent(userAgent, request);
            }
        }

        ClientInfo clientInfo = ClientInfo.builder()
                .channel(channel)
                .device(device)
                .platform(platform)
                .appVersion(appVersion)
                .build();

        log.debug("Resolved client info: channel={}, device={}, platform={}",
                clientInfo.getSafeChannel(),
                clientInfo.getSafeDevice(),
                clientInfo.getSafePlatform());

        return clientInfo;
    }

    /**
     * 从 User-Agent 推断设备类型
     */
    private String inferDeviceFromUserAgent(String userAgent) {
        String ua = userAgent.toLowerCase();

        // 平板检测（在手机之前，因为有些平板 UA 也包含 Mobile）
        if (ua.contains("ipad") || ua.contains("tablet") ||
            (ua.contains("android") && !ua.contains("mobile"))) {
            return ClientInfo.DEVICE_TABLET;
        }

        // 手机检测
        if (ua.contains("mobile") || ua.contains("iphone") ||
            ua.contains("android") || ua.contains("phone")) {
            return ClientInfo.DEVICE_MOBILE;
        }

        // 默认为桌面端
        return ClientInfo.DEVICE_DESKTOP;
    }

    /**
     * 从 User-Agent 推断操作系统/平台
     */
    private String inferPlatformFromUserAgent(String userAgent) {
        String ua = userAgent.toLowerCase();

        if (ua.contains("iphone") || ua.contains("ipad") || ua.contains("ios")) {
            return ClientInfo.PLATFORM_IOS;
        }
        if (ua.contains("android")) {
            return ClientInfo.PLATFORM_ANDROID;
        }
        if (ua.contains("windows")) {
            return ClientInfo.PLATFORM_WINDOWS;
        }
        if (ua.contains("macintosh") || ua.contains("mac os")) {
            return ClientInfo.PLATFORM_MACOS;
        }
        if (ua.contains("linux") && !ua.contains("android")) {
            return ClientInfo.PLATFORM_LINUX;
        }

        return ClientInfo.PLATFORM_UNKNOWN;
    }

    /**
     * 从 User-Agent 和请求信息推断渠道
     */
    private String inferChannelFromUserAgent(String userAgent, HttpServletRequest request) {
        String ua = userAgent.toLowerCase();

        // 微信浏览器
        if (ua.contains("micromessenger") || ua.contains("wechat")) {
            return ClientInfo.CHANNEL_WECHAT;
        }

        // 自定义 App（通过 User-Agent 中的 App 标识）
        if (ua.contains("authplatform-ios") || ua.contains("authplatform/ios")) {
            return ClientInfo.CHANNEL_APP_IOS;
        }
        if (ua.contains("authplatform-android") || ua.contains("authplatform/android")) {
            return ClientInfo.CHANNEL_APP_ANDROID;
        }

        // 检查 Referer 判断是否来自官网
        String referer = request.getHeader("Referer");
        if (referer != null && !referer.isBlank()) {
            // 可以根据实际域名判断
            return ClientInfo.CHANNEL_WEBSITE;
        }

        // 默认为官网
        return ClientInfo.CHANNEL_WEBSITE;
    }
}
