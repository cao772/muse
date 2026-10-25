import Foundation

// Compile once with: swiftc scripts/mac_thermal_state.swift -o /path/to/muse-thermal
// No sudo / SMC access. System thermal-pressure state is NOT a Celsius reading.
if #available(macOS 10.10.3, *) {
    switch ProcessInfo.processInfo.thermalState {
    case .nominal: print("nominal")
    case .fair: print("fair")
    case .serious: print("serious")
    case .critical: print("critical")
    @unknown default: print("unknown")
    }
} else {
    print("unknown")
}
