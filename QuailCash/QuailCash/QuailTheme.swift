import SwiftUI
import UIKit

enum QuailThemeMode: String {
    case system
    case light
    case dark
    case oled
    case solarized
    case forest
    case midnight

    init(rawValue: String) {
        switch rawValue.lowercased() {
        case "light":
            self = .light
        case "dark":
            self = .dark
        case "oled":
            self = .oled
        case "solarized":
            self = .solarized
        case "forest":
            self = .forest
        case "midnight":
            self = .midnight
        default:
            self = .system
        }
    }

    var preferredColorScheme: ColorScheme? {
        switch self {
        case .system:
            return nil
        case .light, .solarized:
            return .light
        case .dark, .oled, .forest, .midnight:
            return .dark
        }
    }
}

struct QuailThemePalette {
    let backgroundTop: Color
    let backgroundBottom: Color
    let surface: Color
    let elevatedSurface: Color
    let border: Color
    let accent: Color
    let positive: Color
    let negative: Color
    let tooltipBackground: Color
    let tooltipText: Color
    let notificationBadge: Color
    let primaryButton: Color
    let primaryButtonText: Color
    let secondaryButton: Color
    let secondaryButtonText: Color
    let chromeIconBackground: Color
    let chromeIconForeground: Color
    let barBackground: Color
    let barDivider: Color
    let selectedTabFill: Color
}

private extension Color {
    static func adaptive(light: Color, dark: Color) -> Color {
        Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })
    }
}

enum QuailTheme {
    static func palette(for rawMode: String) -> QuailThemePalette {
        switch QuailThemeMode(rawValue: rawMode) {
        case .system:
            let light = palette(for: "light")
            let dark = palette(for: "dark")
            return QuailThemePalette(
                backgroundTop:        .adaptive(light: light.backgroundTop,        dark: dark.backgroundTop),
                backgroundBottom:     .adaptive(light: light.backgroundBottom,     dark: dark.backgroundBottom),
                surface:              .adaptive(light: light.surface,              dark: dark.surface),
                elevatedSurface:      .adaptive(light: light.elevatedSurface,      dark: dark.elevatedSurface),
                border:               .adaptive(light: light.border,               dark: dark.border),
                accent:               .adaptive(light: light.accent,               dark: dark.accent),
                positive:             .adaptive(light: light.positive,             dark: dark.positive),
                negative:             .adaptive(light: light.negative,             dark: dark.negative),
                tooltipBackground:    .adaptive(light: light.tooltipBackground,    dark: dark.tooltipBackground),
                tooltipText:          .adaptive(light: light.tooltipText,          dark: dark.tooltipText),
                notificationBadge:    .adaptive(light: light.notificationBadge,    dark: dark.notificationBadge),
                primaryButton:        .adaptive(light: light.primaryButton,        dark: dark.primaryButton),
                primaryButtonText:    .adaptive(light: light.primaryButtonText,    dark: dark.primaryButtonText),
                secondaryButton:      .adaptive(light: light.secondaryButton,      dark: dark.secondaryButton),
                secondaryButtonText:  .adaptive(light: light.secondaryButtonText,  dark: dark.secondaryButtonText),
                chromeIconBackground: .adaptive(light: light.chromeIconBackground, dark: dark.chromeIconBackground),
                chromeIconForeground: .adaptive(light: light.chromeIconForeground, dark: dark.chromeIconForeground),
                barBackground:        .adaptive(light: light.barBackground,        dark: dark.barBackground),
                barDivider:           .adaptive(light: light.barDivider,           dark: dark.barDivider),
                selectedTabFill:      .adaptive(light: light.selectedTabFill,      dark: dark.selectedTabFill)
            )
        case .light:
            return QuailThemePalette(
                backgroundTop: Color(red: 0.98, green: 0.98, blue: 0.99),
                backgroundBottom: Color(red: 0.94, green: 0.95, blue: 0.97),
                surface: .white,
                elevatedSurface: .white,
                border: Color.black.opacity(0.06),
                accent: Color(red: 0.16, green: 0.44, blue: 0.94),
                positive: Color(red: 0.11, green: 0.60, blue: 0.28),
                negative: Color(red: 0.86, green: 0.22, blue: 0.18),
                tooltipBackground: Color.black.opacity(0.82),
                tooltipText: .white,
                notificationBadge: Color.red,
                primaryButton: .black,
                primaryButtonText: .white,
                secondaryButton: .white,
                secondaryButtonText: .primary,
                chromeIconBackground: .white,
                chromeIconForeground: .primary,
                barBackground: .white,
                barDivider: Color.black.opacity(0.12),
                selectedTabFill: .white
            )
        case .dark:
            return QuailThemePalette(
                backgroundTop: Color(red: 0.10, green: 0.11, blue: 0.13),
                backgroundBottom: Color(red: 0.05, green: 0.06, blue: 0.07),
                surface: Color(red: 0.14, green: 0.15, blue: 0.18),
                elevatedSurface: Color(red: 0.17, green: 0.18, blue: 0.21),
                border: Color.white.opacity(0.08),
                accent: Color(red: 0.52, green: 0.72, blue: 1.00),
                positive: Color(red: 0.46, green: 0.85, blue: 0.56),
                negative: Color(red: 1.00, green: 0.48, blue: 0.43),
                tooltipBackground: Color.white.opacity(0.10),
                tooltipText: .white,
                notificationBadge: Color(red: 1.00, green: 0.38, blue: 0.34),
                primaryButton: .white,
                primaryButtonText: .black,
                secondaryButton: Color.white.opacity(0.08),
                secondaryButtonText: .white,
                chromeIconBackground: Color.white.opacity(0.08),
                chromeIconForeground: .white,
                barBackground: Color(red: 0.12, green: 0.13, blue: 0.15),
                barDivider: Color.white.opacity(0.10),
                selectedTabFill: Color.white.opacity(0.08)
            )
        case .oled:
            return QuailThemePalette(
                backgroundTop: .black,
                backgroundBottom: .black,
                surface: Color(red: 0.07, green: 0.07, blue: 0.08),
                elevatedSurface: Color(red: 0.10, green: 0.10, blue: 0.11),
                border: Color.white.opacity(0.10),
                accent: Color(red: 0.57, green: 0.78, blue: 1.00),
                positive: Color(red: 0.46, green: 0.90, blue: 0.56),
                negative: Color(red: 1.00, green: 0.48, blue: 0.43),
                tooltipBackground: Color.white.opacity(0.10),
                tooltipText: .white,
                notificationBadge: Color(red: 1.00, green: 0.38, blue: 0.34),
                primaryButton: .white,
                primaryButtonText: .black,
                secondaryButton: Color.white.opacity(0.08),
                secondaryButtonText: .white,
                chromeIconBackground: Color.white.opacity(0.08),
                chromeIconForeground: .white,
                barBackground: .black,
                barDivider: Color.white.opacity(0.10),
                selectedTabFill: Color.white.opacity(0.08)
            )
        case .solarized:
            return QuailThemePalette(
                backgroundTop: Color(red: 0.99, green: 0.96, blue: 0.88),
                backgroundBottom: Color(red: 0.97, green: 0.92, blue: 0.80),
                surface: Color(red: 1.00, green: 0.98, blue: 0.92),
                elevatedSurface: Color(red: 0.99, green: 0.96, blue: 0.88),
                border: Color(red: 0.73, green: 0.68, blue: 0.55).opacity(0.35),
                accent: Color(red: 0.15, green: 0.38, blue: 0.67),
                positive: Color(red: 0.27, green: 0.52, blue: 0.23),
                negative: Color(red: 0.79, green: 0.25, blue: 0.20),
                tooltipBackground: Color(red: 0.00, green: 0.27, blue: 0.31).opacity(0.88),
                tooltipText: .white,
                notificationBadge: Color(red: 0.86, green: 0.29, blue: 0.24),
                primaryButton: Color(red: 0.00, green: 0.27, blue: 0.31),
                primaryButtonText: .white,
                secondaryButton: Color(red: 0.93, green: 0.89, blue: 0.78),
                secondaryButtonText: Color(red: 0.00, green: 0.27, blue: 0.31),
                chromeIconBackground: Color(red: 1.00, green: 0.98, blue: 0.92),
                chromeIconForeground: Color(red: 0.00, green: 0.27, blue: 0.31),
                barBackground: Color(red: 0.99, green: 0.96, blue: 0.88),
                barDivider: Color(red: 0.73, green: 0.68, blue: 0.55).opacity(0.35),
                selectedTabFill: Color(red: 1.00, green: 0.98, blue: 0.92)
            )
        case .forest:
            return QuailThemePalette(
                backgroundTop: Color(red: 0.08, green: 0.13, blue: 0.10),
                backgroundBottom: Color(red: 0.04, green: 0.08, blue: 0.06),
                surface: Color(red: 0.11, green: 0.17, blue: 0.13),
                elevatedSurface: Color(red: 0.14, green: 0.21, blue: 0.16),
                border: Color(red: 0.56, green: 0.78, blue: 0.63).opacity(0.18),
                accent: Color(red: 0.63, green: 0.87, blue: 0.70),
                positive: Color(red: 0.59, green: 0.92, blue: 0.60),
                negative: Color(red: 1.00, green: 0.55, blue: 0.48),
                tooltipBackground: Color.white.opacity(0.10),
                tooltipText: .white,
                notificationBadge: Color(red: 0.96, green: 0.36, blue: 0.32),
                primaryButton: Color(red: 0.62, green: 0.84, blue: 0.66),
                primaryButtonText: .black,
                secondaryButton: Color.white.opacity(0.08),
                secondaryButtonText: .white,
                chromeIconBackground: Color.white.opacity(0.08),
                chromeIconForeground: .white,
                barBackground: Color(red: 0.09, green: 0.15, blue: 0.11),
                barDivider: Color.white.opacity(0.10),
                selectedTabFill: Color.white.opacity(0.08)
            )
        case .midnight:
            return QuailThemePalette(
                backgroundTop: Color(red: 0.07, green: 0.10, blue: 0.18),
                backgroundBottom: Color(red: 0.03, green: 0.04, blue: 0.08),
                surface: Color(red: 0.10, green: 0.14, blue: 0.23),
                elevatedSurface: Color(red: 0.13, green: 0.18, blue: 0.30),
                border: Color.white.opacity(0.10),
                accent: Color(red: 0.66, green: 0.80, blue: 1.00),
                positive: Color(red: 0.50, green: 0.88, blue: 0.60),
                negative: Color(red: 1.00, green: 0.52, blue: 0.46),
                tooltipBackground: Color.white.opacity(0.10),
                tooltipText: .white,
                notificationBadge: Color(red: 0.98, green: 0.40, blue: 0.35),
                primaryButton: Color(red: 0.66, green: 0.80, blue: 1.00),
                primaryButtonText: .black,
                secondaryButton: Color.white.opacity(0.08),
                secondaryButtonText: .white,
                chromeIconBackground: Color.white.opacity(0.08),
                chromeIconForeground: .white,
                barBackground: Color(red: 0.08, green: 0.11, blue: 0.20),
                barDivider: Color.white.opacity(0.10),
                selectedTabFill: Color.white.opacity(0.08)
            )
        }
    }
}
