import SwiftUI

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

enum QuailTheme {
    static func palette(for rawMode: String) -> QuailThemePalette {
        switch QuailThemeMode(rawValue: rawMode) {
        case .system, .light:
            return QuailThemePalette(
                backgroundTop: Color(red: 0.98, green: 0.98, blue: 0.99),
                backgroundBottom: Color(red: 0.94, green: 0.95, blue: 0.97),
                surface: .white,
                elevatedSurface: .white,
                border: Color.black.opacity(0.06),
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
