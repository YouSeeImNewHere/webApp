import SwiftUI
import MapKit
import CoreLocation
import Combine
import AVFoundation
import HealthKit

// MARK: - Main page

struct RouteMapPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var vm = RouteMapViewModel()

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: "Quail Maps",
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            showsStandaloneBar: true,
            onLeadingTap: { navigator.show(.mapSettings) },
            onTrailingTap: { navigator.show(.notifications) },
            extraTrailingAction: { navigator.show(.mapTripAnalytics) },
            extraTrailingIcon: "chart.bar.fill",
            extraTrailingAction2: { navigator.show(.savedPlaces) },
            extraTrailingIcon2: "bookmark.fill"
        ) {
            RouteMapContent(vm: vm, palette: palette)
        }
    }
}

// MARK: - Map content

private struct RouteMapContent: View {
    @ObservedObject var vm: RouteMapViewModel
    let palette: QuailThemePalette

    var body: some View {
        MapReader { mapProxy in
        ZStack(alignment: .bottom) {
            // Map — fills full content area
            Map(position: $vm.cameraPosition) {
                // Current location
                if let loc = vm.userLocation {
                    Annotation("You", coordinate: loc, anchor: .bottom) {
                        Image(systemName: "location.circle.fill")
                            .font(.system(size: 24, weight: .bold))
                            .foregroundStyle(.blue)
                    }
                }
                // Destination pin
                if let dest = vm.destinationCoordinate {
                    Marker(vm.destinationName, coordinate: dest)
                        .tint(.red)
                }
                // Detour waypoint pins
                ForEach(vm.addedDetours) { detour in
                    Marker(detour.name, systemImage: detour.category.systemImage, coordinate: detour.coordinate)
                        .tint(detour.category.color)
                }
                // Explore result pins
                ForEach(Array(vm.exploreResults.enumerated()), id: \.offset) { _, item in
                    let isSelected = vm.selectedPlace === item
                    Marker(item.name ?? "Place", coordinate: item.placemark.coordinate)
                        .tint(isSelected ? .blue : (vm.exploreCategory?.color ?? .red))
                }
                // Route polylines (all legs)
                ForEach(Array(vm.routeSegments.enumerated()), id: \.offset) { _, seg in
                    MapPolyline(seg.polyline)
                        .stroke(.blue, lineWidth: 4)
                }
                if vm.routeSegments.isEmpty, let route = vm.activeRoute {
                    MapPolyline(route.polyline).stroke(.blue, lineWidth: 4)
                }
                // Isochrone overlays
                if let center = vm.isochroneCenter {
                    // Show approximate circles immediately while API loads
                    if vm.isLoadingIsochrones || vm.isochronePolygons.isEmpty {
                        let speedMPS: Double = vm.isochroneTransport == .walk ? vm.walkingSpeedMPS : 10.0
                        ForEach([60, 50, 40, 30, 20, 10], id: \.self) { minutes in
                            let colorMap: [Int: Color] = [60: .red, 50: Color(red:1,green:0.4,blue:0), 40: .orange, 30: .yellow, 20: Color(red:0.6,green:0.85,blue:0), 10: .green]
                            let color = colorMap[minutes] ?? .blue
                            let radius = Double(minutes) * 60.0 * speedMPS
                            MapCircle(center: center, radius: radius)
                                .foregroundStyle(color.opacity(0.08))
                                .stroke(color.opacity(vm.isLoadingIsochrones ? 0.3 : 0.6), lineWidth: 2)
                        }
                    }
                    // Replace with real road-based polygons when available
                    if !vm.isochronePolygons.isEmpty {
                        ForEach(Array(vm.isochronePolygons.enumerated()), id: \.offset) { _, ring in
                            let colorMap: [Int: Color] = [60: .red, 50: Color(red:1,green:0.4,blue:0), 40: .orange, 30: .yellow, 20: Color(red:0.6,green:0.85,blue:0), 10: .green]
                            let color = colorMap[ring.minutes] ?? .blue
                            MapPolygon(coordinates: ring.coords)
                                .foregroundStyle(color.opacity(0.15))
                                .stroke(color.opacity(0.7), lineWidth: 2)
                        }
                    }
                    Annotation("", coordinate: center) {
                        Circle()
                            .fill(Color.blue)
                            .frame(width: 14, height: 14)
                            .overlay(Circle().stroke(.white, lineWidth: 2))
                    }
                }
            }
            .mapControls {
                MapUserLocationButton()
                MapCompass()
            }
            .ignoresSafeArea(edges: .all)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            // tap captured by overlay below

            // Transparent tap interceptor — only active in isochrone mode
            if vm.isochroneMode && !vm.isLoadingIsochrones {
                Color.clear
                    .contentShape(Rectangle())
                    .ignoresSafeArea()
                    .onTapGesture { point in
                        if let coord = mapProxy.convert(point, from: .local) {
                            vm.setIsochroneCenter(coord)
                            let span: Double = vm.isochroneTransport == .drive ? 60_000 : 12_000
                            vm.cameraPosition = .region(MKCoordinateRegion(center: coord, latitudinalMeters: span, longitudinalMeters: span))
                        }
                    }
            }

            // Isochrone panel
            if vm.isochroneMode {
                IsochronePanel(vm: vm, palette: palette)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            } else if vm.isNavigating {
                NavigationOverlay(vm: vm, palette: palette)
            } else {
                // Bottom panel
                RoutePanel(vm: vm, palette: palette)
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                    .shadow(color: .black.opacity(0.12), radius: 12, y: -4)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)

                // Place detail card — floats above the panel
                if let place = vm.selectedPlace {
                    PlaceDetailCard(item: place, palette: palette) {
                        vm.routeToPlace(place)
                    } onDismiss: {
                        vm.selectedPlace = nil
                    }
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
        }
        .overlay(alignment: .topTrailing) {
            // Isochrone toggle — top right floating button
            Button { withAnimation(.spring(response: 0.3)) { vm.toggleIsochroneMode() } } label: {
                Image(systemName: vm.isochroneMode ? "clock.fill" : "clock")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(vm.isochroneMode ? .white : palette.chromeIconForeground)
                    .frame(width: 38, height: 38)
                    .background(vm.isochroneMode ? Color.purple : palette.chromeIconBackground, in: Circle())
                    .overlay(Circle().stroke(palette.border, lineWidth: 1))
                    .shadow(radius: 4)
            }
            .buttonStyle(.plain)
            .padding(.top, 8)
            .padding(.trailing, 12)
        }
        .animation(.spring(response: 0.3, dampingFraction: 0.85), value: vm.selectedPlace != nil)
        .animation(.spring(response: 0.3, dampingFraction: 0.85), value: vm.isochroneMode)
        .onAppear { vm.requestLocation() }
        .sheet(isPresented: $vm.showingSearchSheet) {
            LocationSearchSheet(vm: vm, palette: palette)
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $vm.showingDetourPicker) {
            DetourPickerSheet(vm: vm, palette: palette)
                .presentationDetents([.medium, .large])
        }
        } // MapReader
    }
}

// MARK: - MKPolyline helper

extension MKPolyline {
    nonisolated var allCoordinates: [CLLocationCoordinate2D] {
        var coords = [CLLocationCoordinate2D](repeating: .init(), count: pointCount)
        getCoordinates(&coords, range: NSRange(location: 0, length: pointCount))
        return coords
    }
}

// MARK: - Bottom route panel

private struct RoutePanel: View {
    @ObservedObject var vm: RouteMapViewModel
    let palette: QuailThemePalette
    @State private var isCollapsed = false
    @GestureState private var dragOffset: CGFloat = 0

    private var panelHeight: CGFloat {
        let base: CGFloat
        if isCollapsed { base = 90 }
        else if vm.mapMode == .explore { base = vm.exploreResults.isEmpty ? 320 : 520 }
        else { base = vm.destinationName.isEmpty ? 220 : 560 }
        return max(90, base - max(0, dragOffset))
    }

    var body: some View {
        VStack(spacing: 0) {
            // Drag handle
            Capsule()
                .fill(Color.secondary.opacity(0.4))
                .frame(width: 36, height: 4)
                .padding(.top, 10)
                .padding(.bottom, 8)
                .gesture(
                    DragGesture()
                        .updating($dragOffset) { value, state, _ in state = value.translation.height }
                        .onEnded { value in
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                if value.translation.height > 60 { isCollapsed = true }
                                else if value.translation.height < -40 { isCollapsed = false }
                            }
                        }
                )
                .onTapGesture {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { isCollapsed.toggle() }
                }

            // Completed trip banner
            if let miles = vm.completedTripMiles {
                let currentMi = VehicleStore.shared.profile.currentMileage
                let newMi = currentMi + Int(miles.rounded())
                VStack(spacing: 6) {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Trip complete · \(String(format: "%.1f", miles)) mi")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                            if !vm.completedTripDestination.isEmpty {
                                Text("to \(vm.completedTripDestination)")
                                    .font(.system(size: 11, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Button {
                            vm.completedTripMiles = nil
                        } label: {
                            Image(systemName: "xmark").font(.system(size: 12, weight: .bold)).foregroundStyle(.secondary)
                        }.buttonStyle(.plain)
                    }
                    if currentMi > 0 {
                        Button {
                            vm.confirmOdometerUpdate()
                        } label: {
                            Text("Update odometer → \(newMi.formatted()) mi")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(.white)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 7)
                                .background(Color.blue, in: RoundedRectangle(cornerRadius: 8))
                        }.buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Color.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                .padding(.horizontal, 10)
                .padding(.bottom, 4)
            }

            // Mode toggle
            HStack(spacing: 0) {
                modePill("Route", icon: "arrow.triangle.turn.up.right.road.fill", mode: .route)
                modePill("Explore", icon: "magnifyingglass.circle.fill", mode: .explore)
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 8)

        ScrollView(showsIndicators: false) {
            VStack(spacing: 0) {
                Color.clear.frame(height: 0) // spacer so ScrollView doesn't eat the handle

                if vm.mapMode == .explore {
                    ExplorePanel(vm: vm, palette: palette)
                } else {

                // From / To
                VStack(spacing: 10) {
                    LocationRow(icon: "location.fill", iconColor: .blue,
                                placeholder: "Starting location",
                                value: vm.originName.isEmpty ? nil : vm.originName,
                                palette: palette) {
                        vm.searchTarget = .origin; vm.showingSearchSheet = true
                    }
                    HStack {
                        Rectangle().fill(palette.border).frame(height: 1)
                        Button { vm.swapLocations() } label: {
                            Image(systemName: "arrow.up.arrow.down")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(palette.chromeIconForeground)
                                .frame(width: 30, height: 30)
                                .background(palette.chromeIconBackground, in: Circle())
                                .overlay(Circle().stroke(palette.border, lineWidth: 1))
                        }.buttonStyle(.plain)
                        Rectangle().fill(palette.border).frame(height: 1)
                    }
                    LocationRow(icon: "mappin.circle.fill", iconColor: .red,
                                placeholder: "Destination",
                                value: vm.destinationName.isEmpty ? nil : vm.destinationName,
                                palette: palette) {
                        vm.searchTarget = .destination; vm.showingSearchSheet = true
                    }
                }
                .padding(.horizontal, 14)

                if !vm.destinationName.isEmpty {
                    Divider().padding(.vertical, 10)

                    // Schedule + transport toggle
                    HStack(spacing: 10) {
                        // Schedule button
                        Button { vm.showingTimePicker.toggle() } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                // Leave at / Arrive by toggle inline
                                HStack(spacing: 0) {
                                    schedModeChip("Leave at", mode: .leaveAt)
                                    schedModeChip("Arrive by", mode: .arriveBy)
                                }
                                Text(vm.scheduleTime, format: .dateTime.weekday(.abbreviated).hour().minute())
                                    .font(.system(size: 13, weight: .bold, design: .rounded))
                                    .foregroundStyle(palette.primaryButton)
                            }
                            .padding(.horizontal, 10).padding(.vertical, 7)
                            .background(palette.primaryButton.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(palette.primaryButton.opacity(0.25), lineWidth: 1))
                        }.buttonStyle(.plain)

                        Spacer()

                        HStack(spacing: 0) {
                            transportChip("car.fill", label: "Drive", type: .automobile)
                            transportChip("tram.fill", label: "Transit", type: .transit)
                        }
                        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(palette.border, lineWidth: 1))
                    }
                    .padding(.horizontal, 14)

                    if vm.showingTimePicker {
                        DatePicker("", selection: $vm.scheduleTime, in: Date()..., displayedComponents: [.date, .hourAndMinute])
                            .datePickerStyle(.compact)
                            .labelsHidden()
                            .padding(.horizontal, 14)
                            .padding(.top, 4)
                            .onChange(of: vm.scheduleTime) { _, _ in vm.triggerRecalculate() }
                    }

                    // Route alternatives
                    if !vm.alternativeRoutes.isEmpty {
                        Divider().padding(.vertical, 8)
                        VStack(spacing: 6) {
                            ForEach(Array(vm.alternativeRoutes.enumerated()), id: \.offset) { idx, route in
                                RouteOptionCard(
                                    route: route,
                                    index: idx,
                                    isSelected: idx == vm.activeRouteIndex,
                                    departBy: vm.departBy(for: route),
                                    arriveAt: vm.arriveAt(for: route),
                                    scheduleMode: vm.scheduleMode,
                                    isTransit: vm.transportType == .transit,
                                    palette: palette
                                ) { vm.selectRoute(index: idx) }
                            }
                        }
                        .padding(.horizontal, 14)
                    } else if !vm.originName.isEmpty {
                        HStack { Spacer(); ProgressView(); Spacer() }.padding(.vertical, 12)
                    } else {
                        Text("Set a starting location to see routes")
                            .font(.system(size: 12, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                    }

                    // Traffic badge
                    if !vm.alternativeRoutes.isEmpty && vm.routeTraffic != .unknown {
                        HStack(spacing: 6) {
                            Image(systemName: vm.routeTraffic.icon)
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(vm.routeTraffic.color)
                            Text(vm.routeTraffic.label)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(vm.routeTraffic.color)
                            Text("along your route")
                                .font(.system(size: 12, design: .rounded))
                                .foregroundStyle(.secondary)
                            Spacer()
                        }
                        .padding(.horizontal, 14)
                        .padding(.top, 2)
                    }

                    // Stops along the way
                    Divider().padding(.vertical, 8)
                    VStack(alignment: .leading, spacing: 10) {
                        Text("STOPS ALONG THE WAY")
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 14)

                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(DetourCategory.allCases) { cat in
                                    let isActive = vm.activeDetourCategories.contains(cat)
                                    Button { vm.toggleDetourCategory(cat) } label: {
                                        HStack(spacing: 5) {
                                            Image(systemName: cat.systemImage).font(.system(size: 12, weight: .semibold))
                                            Text(cat.label).font(.system(size: 13, weight: .semibold, design: .rounded))
                                        }
                                        .foregroundStyle(isActive ? .white : cat.color)
                                        .padding(.horizontal, 12).padding(.vertical, 7)
                                        .background(isActive ? cat.color : cat.color.opacity(0.12), in: Capsule())
                                    }.buttonStyle(.plain)
                                }
                            }
                            .padding(.horizontal, 14)
                        }

                        ForEach(DetourCategory.allCases) { cat in
                            if vm.activeDetourCategories.contains(cat) {
                                let key = cat.rawValue
                                VStack(alignment: .leading, spacing: 4) {
                                    if vm.loadingDetourCategories.contains(key) {
                                        HStack(spacing: 8) {
                                            ProgressView().scaleEffect(0.8)
                                            Text("Finding \(cat.label.lowercased())…")
                                                .font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
                                        }.padding(.horizontal, 14)
                                    } else if let results = vm.inlineDetourResults[key], !results.isEmpty {
                                        ForEach(results) { candidate in
                                            DetourResultRow(candidate: candidate, palette: palette) {
                                                vm.addDetour(candidate)
                                                vm.activeDetourCategories.remove(cat)
                                                vm.inlineDetourResults.removeValue(forKey: key)
                                            }
                                            .padding(.horizontal, 14)
                                        }
                                        Button { vm.expandDetourThreshold(for: cat) } label: {
                                            HStack(spacing: 4) {
                                                Image(systemName: "arrow.up.left.and.arrow.down.right").font(.system(size: 11))
                                                Text("Expand search radius").font(.system(size: 12, weight: .medium, design: .rounded))
                                            }
                                            .foregroundStyle(.secondary).padding(.horizontal, 14).padding(.top, 2)
                                        }.buttonStyle(.plain)
                                    } else {
                                        Text("No \(cat.label.lowercased()) spots found nearby.")
                                            .font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
                                            .padding(.horizontal, 14)
                                        Button { vm.expandDetourThreshold(for: cat) } label: {
                                            HStack(spacing: 4) {
                                                Image(systemName: "arrow.up.left.and.arrow.down.right").font(.system(size: 11))
                                                Text("Expand search radius").font(.system(size: 12, weight: .medium, design: .rounded))
                                            }
                                            .foregroundStyle(palette.primaryButton).padding(.horizontal, 14).padding(.top, 2)
                                        }.buttonStyle(.plain)
                                    }
                                }
                            }
                        }
                    }

                    // Added stops
                    if !vm.addedDetours.isEmpty {
                        Divider().padding(.top, 8)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(vm.addedDetours) { detour in
                                    HStack(spacing: 6) {
                                        Image(systemName: detour.category.systemImage)
                                            .font(.system(size: 11, weight: .semibold))
                                            .foregroundStyle(detour.category.color)
                                        Text(detour.name)
                                            .font(.system(size: 12, weight: .medium, design: .rounded))
                                            .lineLimit(1)
                                        Button { vm.removeDetour(detour) } label: {
                                            Image(systemName: "xmark").font(.system(size: 10, weight: .bold)).foregroundStyle(.secondary)
                                        }.buttonStyle(.plain)
                                    }
                                    .padding(.horizontal, 10).padding(.vertical, 6)
                                    .background(Color.secondary.opacity(0.12), in: Capsule())
                                }
                            }
                            .padding(.horizontal, 14).padding(.vertical, 8)
                        }
                    }

                    // Go button
                    HStack(spacing: 10) {
                        Button {
                            if vm.originCoordinate == nil { vm.useCurrentLocationAsOrigin() }
                            vm.startNavigation()
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "arrow.triangle.turn.up.right.circle.fill")
                                Text("Go")
                            }
                            .font(.system(size: 15, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 13)
                            .background(Color.blue, in: RoundedRectangle(cornerRadius: 14))
                        }
                        .buttonStyle(.plain)
                        .disabled(vm.activeRoute == nil)

                        Button { vm.openInMaps() } label: {
                            Image(systemName: "arrow.up.right.square")
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundStyle(.secondary)
                                .frame(width: 48, height: 48)
                                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 14)
                    .padding(.top, 8)
                }

                Spacer(minLength: 0).frame(height: 16)
                } // end else (route mode)
            }
        }
        .frame(maxWidth: .infinity)
        } // end outer VStack
        .frame(maxWidth: .infinity)
        .frame(height: panelHeight)
        .clipped()
        .animation(.spring(response: 0.3, dampingFraction: 0.8), value: isCollapsed)
    }

    @ViewBuilder private func schedModeChip(_ label: String, mode: ScheduleMode) -> some View {
        let isSelected = vm.scheduleMode == mode
        Button {
            vm.scheduleMode = mode
            vm.triggerRecalculate()
        } label: {
            Text(label)
                .font(.system(size: 9, weight: .bold, design: .rounded))
                .foregroundStyle(isSelected ? palette.primaryButton : .secondary)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(isSelected ? palette.primaryButton.opacity(0.12) : Color.clear, in: Capsule())
        }.buttonStyle(.plain)
    }

    @ViewBuilder private func transportChip(_ icon: String, label: String, type: MKDirectionsTransportType) -> some View {
        let isSelected = vm.transportType == type
        Button {
            vm.transportType = type
            vm.triggerRecalculate()
        } label: {
            HStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 11, weight: .semibold))
                Text(label).font(.system(size: 12, weight: .semibold, design: .rounded))
            }
            .foregroundStyle(isSelected ? .white : palette.chromeIconForeground)
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(isSelected ? Color.blue : Color.clear, in: RoundedRectangle(cornerRadius: 8))
        }.buttonStyle(.plain)
    }

    @ViewBuilder private func modePill(_ label: String, icon: String, mode: MapPanelMode) -> some View {
        let isSelected = vm.mapMode == mode
        Button {
            withAnimation(.spring(response: 0.25, dampingFraction: 0.8)) {
                vm.mapMode = mode
                if mode == .route { vm.clearExplore() }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: 12, weight: .semibold))
                Text(label).font(.system(size: 13, weight: .semibold, design: .rounded))
            }
            .foregroundStyle(isSelected ? .white : palette.chromeIconForeground)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(isSelected ? Color.blue : Color.clear, in: RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(palette.border, lineWidth: 1))
    }
}

// MARK: - Explore panel

private struct ExplorePanel: View {
    @ObservedObject var vm: RouteMapViewModel
    let palette: QuailThemePalette
    @State private var query = ""
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Search bar
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Search restaurants, stores…", text: $query)
                    .font(.system(size: 14, design: .rounded))
                    .focused($focused)
                    .autocorrectionDisabled()
                    .submitLabel(.search)
                    .onSubmit { vm.searchPlaces(query: query) }
                    .onChange(of: query) { _, q in
                        if q.isEmpty { vm.exploreResults = []; vm.exploreCategory = nil }
                    }
                if !query.isEmpty {
                    Button { query = ""; vm.clearExplore(); focused = false } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                    }.buttonStyle(.plain)
                }
                if vm.isExploring { ProgressView().scaleEffect(0.75) }
            }
            .padding(.horizontal, 12).padding(.vertical, 10)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(palette.border, lineWidth: 1))
            .padding(.horizontal, 14)

            // Category chips
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(ExploreCategory.allCases) { cat in
                        let isActive = vm.exploreCategory == cat
                        Button {
                            focused = false
                            query = ""
                            if isActive { vm.clearExplore() } else { vm.searchCategory(cat) }
                        } label: {
                            HStack(spacing: 5) {
                                Image(systemName: cat.icon).font(.system(size: 12, weight: .semibold))
                                Text(cat.label).font(.system(size: 13, weight: .semibold, design: .rounded))
                            }
                            .foregroundStyle(isActive ? .white : cat.color)
                            .padding(.horizontal, 12).padding(.vertical, 7)
                            .background(isActive ? cat.color : cat.color.opacity(0.12), in: Capsule())
                        }.buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 14)
            }

            // Results
            if vm.exploreResults.isEmpty && !vm.isExploring {
                VStack(spacing: 6) {
                    Image(systemName: "map.fill")
                        .font(.system(size: 28)).foregroundStyle(.secondary.opacity(0.4))
                    Text("Search or pick a category")
                        .font(.system(size: 13, design: .rounded)).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 24)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(vm.exploreResults.enumerated()), id: \.offset) { idx, item in
                        PlaceRow(item: item, userLocation: vm.userLocation, isSelected: vm.selectedPlace === item, palette: palette) {
                            vm.selectedPlace = item
                            let coord = item.placemark.coordinate
                            vm.cameraPosition = .region(MKCoordinateRegion(center: coord, latitudinalMeters: 800, longitudinalMeters: 800))
                        } onDirections: {
                            vm.routeToPlace(item)
                        }
                        if idx < vm.exploreResults.count - 1 {
                            Divider().padding(.leading, 52)
                        }
                    }
                }
                .padding(.horizontal, 14)
            }
        }
        .padding(.bottom, 8)
    }
}

private struct PlaceRow: View {
    let item: MKMapItem
    let userLocation: CLLocationCoordinate2D?
    let isSelected: Bool
    let palette: QuailThemePalette
    let onTap: () -> Void
    let onDirections: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: onTap) {
                HStack(spacing: 12) {
                    Image(systemName: poiIcon(for: item.pointOfInterestCategory))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(poiColor(for: item.pointOfInterestCategory), in: RoundedRectangle(cornerRadius: 8))

                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.name ?? "Place")
                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                            .lineLimit(1)
                        if let addr = item.placemark.title {
                            Text(addr)
                                .font(.system(size: 11, design: .rounded))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                    Spacer()
                    if let dist = distanceText {
                        Text(dist)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            Button(action: onDirections) {
                Image(systemName: "arrow.triangle.turn.up.right.circle.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(Color.blue)
            }
            .buttonStyle(.plain)
        }
        .padding(.vertical, 10)
        .background(isSelected ? Color.blue.opacity(0.06) : Color.clear)
    }

    private var distanceText: String? {
        guard let userLoc = userLocation else { return nil }
        let from = CLLocation(latitude: userLoc.latitude, longitude: userLoc.longitude)
        let to = CLLocation(latitude: item.placemark.coordinate.latitude, longitude: item.placemark.coordinate.longitude)
        return formatDistance(from.distance(from: to))
    }
}

private struct PlaceDetailCard: View {
    let item: MKMapItem
    let palette: QuailThemePalette
    let onDirections: () -> Void
    let onDismiss: () -> Void

    @State private var showSaveSheet = false

    private static let gasBrands: Set<String> = [
        "shell","chevron","arco","76","bp","exxon","mobil","valero",
        "texaco","sunoco","citgo","marathon","sinclair","phillips","speedway",
        "circle k","casey","kwik","raceway","wawa","sheetz","pilot","loves"
    ]

    private var isGasStation: Bool {
        let raw = (item.pointOfInterestCategory?.rawValue ?? "").lowercased()
        let name = (item.name ?? "").lowercased()
        if raw.contains("gas") || raw.contains("petrol") || raw.contains("fuel") { return true }
        if name.contains("gas") || name.contains("fuel") { return true }
        return Self.gasBrands.contains(where: { name.contains($0) })
    }

    private var gasBuddyURL: URL? {
        // Search GasBuddy by station name + city
        let name = (item.name ?? "").addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        let city = (item.placemark.locality ?? "").addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        return URL(string: "https://www.gasbuddy.com/home?search=\(name)+\(city)")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(item.name ?? "Place")
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                    if let addr = item.placemark.title {
                        Text(addr)
                            .font(.system(size: 12, design: .rounded))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                }
                Spacer()
                Button(action: onDismiss) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(.secondary)
                }.buttonStyle(.plain)
            }

            HStack(spacing: 10) {
                if let phone = item.phoneNumber,
                   let phoneURL = URL(string: "tel:\(phone.filter { "0123456789+".contains($0) })") {
                    Link(destination: phoneURL) {
                        Label(phone, systemImage: "phone.fill")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.green)
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Color.green.opacity(0.1), in: Capsule())
                    }
                }
                if let url = item.url {
                    Link(destination: url) {
                        Label("Website", systemImage: "safari.fill")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Color.blue.opacity(0.1), in: Capsule())
                    }
                }
                if isGasStation, let gasBuddyURL = gasBuddyURL {
                    Link(destination: gasBuddyURL) {
                        Label("Gas prices", systemImage: "fuelpump.fill")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.orange)
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Color.orange.opacity(0.1), in: Capsule())
                    }
                }
            }

            HStack(spacing: 8) {
                Button(action: onDirections) {
                    Label("Directions", systemImage: "arrow.triangle.turn.up.right.circle.fill")
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .background(Color.blue, in: RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.plain)

                Button { showSaveSheet = true } label: {
                    Image(systemName: "bookmark.fill")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 44, height: 44)
                        .background(Color.purple, in: RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.plain)
            }
        }
        .padding(14)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .shadow(color: .black.opacity(0.15), radius: 12, y: -4)
        .padding(.horizontal, 4).padding(.bottom, 4)
        .sheet(isPresented: $showSaveSheet) {
            SaveToListSheet(
                placeName: item.name ?? "Place",
                address: item.placemark.title ?? "",
                latitude: item.placemark.coordinate.latitude,
                longitude: item.placemark.coordinate.longitude
            )
        }
    }
}

private struct SaveToListSheet: View {
    let placeName: String
    let address: String
    let latitude: Double
    let longitude: Double

    @Environment(\.dismiss) private var dismiss
    @StateObject private var store = SavedPlacesStore.shared
    @State private var selectedListId: Int? = nil
    @State private var showNewList = false
    @State private var newListName = ""
    @State private var newListEmoji = "📍"
    @State private var saving = false
    @State private var saved = false

    private let colorOptions = ["#5856D6","#FF3B30","#FF9500","#34C759","#007AFF","#AF52DE","#FF2D55"]
    @State private var selectedColor = "#5856D6"

    var body: some View {
        NavigationView {
            List {
                if store.lists.isEmpty && !showNewList {
                    Section {
                        Text("No lists yet. Create one below.")
                            .foregroundStyle(.secondary)
                            .font(.system(size: 14, design: .rounded))
                    }
                }

                if !store.lists.isEmpty {
                    Section("Save to list") {
                        ForEach(store.lists) { list in
                            Button {
                                selectedListId = list.id
                                Task { await saveTo(listId: list.id) }
                            } label: {
                                HStack {
                                    Text(list.emoji)
                                    Text(list.name)
                                        .font(.system(size: 15, design: .rounded))
                                    Spacer()
                                    if selectedListId == list.id && saved {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(.green)
                                    }
                                    Text("\(list.placeCount) places")
                                        .font(.system(size: 12, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .disabled(saving)
                        }
                    }
                }

                Section {
                    if showNewList {
                        HStack {
                            TextField("List name", text: $newListName)
                                .font(.system(size: 15, design: .rounded))
                            Spacer()
                            TextField("📍", text: $newListEmoji)
                                .frame(width: 36)
                                .multilineTextAlignment(.center)
                        }
                        HStack(spacing: 8) {
                            ForEach(colorOptions, id: \.self) { hex in
                                Circle()
                                    .fill(Color(hex: hex) ?? .purple)
                                    .frame(width: 24, height: 24)
                                    .overlay(Circle().stroke(selectedColor == hex ? Color.primary : Color.clear, lineWidth: 2))
                                    .onTapGesture { selectedColor = hex }
                            }
                        }
                        Button("Create & Save") {
                            guard !newListName.isEmpty else { return }
                            Task {
                                await store.createList(name: newListName, emoji: newListEmoji.isEmpty ? "📍" : newListEmoji, color: selectedColor)
                                if let newList = store.lists.last {
                                    await saveTo(listId: newList.id)
                                }
                            }
                        }
                        .disabled(newListName.isEmpty || saving)
                    } else {
                        Button { withAnimation { showNewList = true } } label: {
                            Label("New list", systemImage: "plus.circle.fill")
                                .font(.system(size: 14, weight: .medium, design: .rounded))
                        }
                    }
                }
            }
            .navigationTitle("Save \"\(placeName)\"")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .task { await store.refresh() }
        }
    }

    private func saveTo(listId: Int) async {
        saving = true
        _ = await store.savePlace(
            listId: listId, name: placeName, address: address,
            latitude: latitude, longitude: longitude
        )
        saving = false
        saved = true
        try? await Task.sleep(nanoseconds: 700_000_000)
        dismiss()
    }
}

private func poiIcon(for category: MKPointOfInterestCategory?) -> String {
    guard let raw = category?.rawValue else { return "mappin.fill" }
    if raw.contains("Restaurant") || raw.contains("Bakery") || raw.contains("Cafe") || raw.contains("Food") { return "fork.knife" }
    if raw.contains("Gas") || raw.contains("EVCharging") { return "fuelpump.fill" }
    if raw.contains("Hospital") || raw.contains("Pharmacy") { return "cross.fill" }
    if raw.contains("Hotel") || raw.contains("Lodging") { return "bed.double.fill" }
    if raw.contains("Store") || raw.contains("Clothing") || raw.contains("Bookstore") { return "bag.fill" }
    if raw.contains("Brewery") || raw.contains("Winery") || raw.contains("Nightlife") || raw.contains("Bar") { return "wineglass.fill" }
    if raw.contains("Theater") || raw.contains("Movie") || raw.contains("Museum") { return "theatermasks.fill" }
    if raw.contains("Park") { return "leaf.fill" }
    if raw.contains("Beach") { return "umbrella.fill" }
    if raw.contains("Airport") { return "airplane" }
    return "mappin.fill"
}

private func poiColor(for category: MKPointOfInterestCategory?) -> Color {
    guard let raw = category?.rawValue else { return .gray }
    if raw.contains("Restaurant") || raw.contains("Bakery") || raw.contains("Cafe") || raw.contains("Food") { return .red }
    if raw.contains("Gas") || raw.contains("EVCharging") { return .orange }
    if raw.contains("Hospital") || raw.contains("Pharmacy") { return .teal }
    if raw.contains("Hotel") || raw.contains("Lodging") { return .indigo }
    if raw.contains("Store") || raw.contains("Clothing") || raw.contains("Bookstore") { return .pink }
    if raw.contains("Brewery") || raw.contains("Winery") || raw.contains("Nightlife") || raw.contains("Bar") { return Color(hue: 0.13, saturation: 0.8, brightness: 0.9) }
    if raw.contains("Theater") || raw.contains("Movie") || raw.contains("Museum") { return .purple }
    if raw.contains("Park") { return .green }
    return .gray
}

private struct RouteOptionCard: View {
    let route: MKRoute
    let index: Int
    let isSelected: Bool
    let departBy: Date
    let arriveAt: Date
    let scheduleMode: ScheduleMode
    let isTransit: Bool
    let palette: QuailThemePalette
    let onTap: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Button(action: onTap) {
                HStack(spacing: 12) {
                    Text("\(index + 1)")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .foregroundStyle(isSelected ? .white : .secondary)
                        .frame(width: 24, height: 24)
                        .background(isSelected ? Color.blue : Color.secondary.opacity(0.15), in: Circle())

                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text(formatDuration(route.expectedTravelTime))
                                .font(.system(size: 14, weight: .bold, design: .rounded))
                            if !isTransit {
                                Text("·").foregroundStyle(.secondary)
                                Text(formatDistance(route.distance))
                                    .font(.system(size: 13, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        if isTransit {
                            // Show transit mode icons — walk, bus, ferry etc
                            TransitModeLine(steps: route.steps)
                        } else if !route.name.isEmpty {
                            Text("via \(route.name)")
                                .font(.system(size: 11, design: .rounded))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }

                    Spacer(minLength: 4)

                    VStack(alignment: .trailing, spacing: 2) {
                        Text(scheduleMode == .leaveAt ? "Arrive" : (isTransit ? "Depart" : "Leave by"))
                            .font(.system(size: 9, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        Text(scheduleMode == .leaveAt ? arriveAt : departBy, format: .dateTime.hour().minute())
                            .font(.system(size: 13, weight: .bold, design: .rounded))
                            .foregroundStyle((scheduleMode == .arriveBy && departBy < Date()) ? .red : palette.chromeIconForeground)
                    }
                }
                .padding(12)
            }
            .buttonStyle(.plain)

            // Transit leg breakdown — only when transit mode selected
            if isSelected && isTransit {
                let legs = TransitLeg.from(steps: route.steps)
                if legs.contains(where: { $0.isPublicTransit }) {
                    TransitLegsView(legs: legs, palette: palette)
                        .padding(.horizontal, 12).padding(.bottom, 12)
                } else {
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 11))
                            .foregroundStyle(.orange)
                        Text("No public transit found — try a different time or location")
                            .font(.system(size: 11, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 12).padding(.bottom, 10)
                }
            }
        }
        .background(
            isSelected ? Color.blue.opacity(0.08) : palette.elevatedSurface,
            in: RoundedRectangle(cornerRadius: 10, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(isSelected ? Color.blue : palette.border, lineWidth: isSelected ? 1.5 : 1)
        )
    }
}

// Compact icon row showing walk › bus › ferry etc
private struct TransitModeLine: View {
    let steps: [MKRoute.Step]
    var body: some View {
        let legs = Array(TransitLeg.from(steps: steps).prefix(7))
        HStack(spacing: 4) {
            ForEach(Array(legs.enumerated()), id: \.offset) { idx, leg in
                Image(systemName: leg.icon)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(leg.color)
                if idx < legs.count - 1 {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 8))
                        .foregroundStyle(.secondary.opacity(0.4))
                }
            }
        }
    }
}

// Full leg-by-leg breakdown with connector line
private struct TransitLegsView: View {
    let legs: [TransitLeg]
    let palette: QuailThemePalette

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Divider().padding(.bottom, 10)
            ForEach(Array(legs.enumerated()), id: \.offset) { idx, leg in
                HStack(alignment: .top, spacing: 10) {
                    VStack(spacing: 0) {
                        Image(systemName: leg.icon)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(.white)
                            .frame(width: 26, height: 26)
                            .background(leg.color, in: Circle())
                        if idx < legs.count - 1 {
                            Rectangle()
                                .fill(Color.secondary.opacity(0.25))
                                .frame(width: 2).frame(minHeight: 16)
                        }
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(leg.title)
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                        if let sub = leg.subtitle {
                            Text(sub)
                                .font(.system(size: 11, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.bottom, idx < legs.count - 1 ? 10 : 0)
                    Spacer()
                }
            }
        }
    }
}

// Model that groups consecutive steps into meaningful legs
private struct TransitLeg {
    let title: String
    let subtitle: String?
    let icon: String
    let color: Color
    let isPublicTransit: Bool

    static func from(steps: [MKRoute.Step]) -> [TransitLeg] {
        var legs: [TransitLeg] = []
        var walkDistance: Double = 0
        var walkInstructions: [String] = []

        func flushWalk() {
            guard walkDistance > 0 || !walkInstructions.isEmpty else { return }
            legs.append(TransitLeg(
                title: "Walk",
                subtitle: walkDistance > 0 ? formatDistance(walkDistance) : nil,
                icon: "figure.walk",
                color: .gray,
                isPublicTransit: false
            ))
            walkDistance = 0
            walkInstructions = []
        }

        for step in steps {
            let lower = step.instructions.lowercased()
            let isWalking = step.transportType == .walking
                || lower.hasPrefix("walk")
                || lower.hasPrefix("head ")
                || lower.hasPrefix("proceed")
                || lower.hasPrefix("turn ")
                || lower.hasPrefix("at the ")
                || lower.hasPrefix("continue")
                || lower.hasPrefix("keep ")
                || lower.hasPrefix("merge")
                || lower.hasPrefix("take the exit")
                || lower.hasPrefix("arrive")

            if isWalking {
                walkDistance += step.distance
                if !step.instructions.isEmpty { walkInstructions.append(step.instructions) }
            } else {
                flushWalk()
                let leg = transitLeg(from: step)
                legs.append(leg)
            }
        }
        flushWalk()
        return legs
    }

    private static func transitLeg(from step: MKRoute.Step) -> TransitLeg {
        let raw = step.instructions
        let lower = raw.lowercased()
        if lower.contains("ferry") || lower.contains("boat") {
            return TransitLeg(title: raw, subtitle: step.distance > 0 ? formatDistance(step.distance) : nil,
                              icon: "ferry.fill", color: .blue, isPublicTransit: true)
        } else if lower.contains("train") || lower.contains("rail") || lower.contains("subway") || lower.contains("metro") || lower.contains("amtrak") {
            return TransitLeg(title: raw, subtitle: step.distance > 0 ? formatDistance(step.distance) : nil,
                              icon: "tram.fill", color: .purple, isPublicTransit: true)
        } else if lower.contains("tram") || lower.contains("streetcar") || lower.contains("light rail") {
            return TransitLeg(title: raw, subtitle: step.distance > 0 ? formatDistance(step.distance) : nil,
                              icon: "tram.circle.fill", color: .green, isPublicTransit: true)
        } else if lower.contains("bus") {
            return TransitLeg(title: raw, subtitle: step.distance > 0 ? formatDistance(step.distance) : nil,
                              icon: "bus.fill", color: .orange, isPublicTransit: true)
        } else {
            return TransitLeg(title: raw, subtitle: step.distance > 0 ? formatDistance(step.distance) : nil,
                              icon: "figure.walk", color: .gray, isPublicTransit: false)
        }
    }
}

// MARK: - Navigation overlay

private struct NavigationOverlay: View {
    @ObservedObject var vm: RouteMapViewModel
    let palette: QuailThemePalette

    var body: some View {
        VStack(spacing: 0) {
            // Top instruction banner
            VStack(alignment: .leading, spacing: 6) {
                if let route = vm.activeRoute, vm.currentStepIndex < route.steps.count {
                    let step = route.steps[vm.currentStepIndex]

                    HStack(alignment: .top, spacing: 12) {
                        maneuverIcon(for: step.instructions)
                            .font(.system(size: 28, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 44, height: 44)
                            .background(Color.blue, in: Circle())

                        VStack(alignment: .leading, spacing: 3) {
                            Text(step.instructions)
                                .font(.system(size: 20, weight: .bold, design: .rounded))
                                .foregroundStyle(.primary)
                                .lineLimit(2)
                            if vm.distanceToNextStep > 0 {
                                Text("in \(formatDistance(vm.distanceToNextStep))")
                                    .font(.system(size: 14, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                    }

                    // Next step preview
                    if vm.currentStepIndex + 1 < route.steps.count {
                        let nextStep = route.steps[vm.currentStepIndex + 1]
                        HStack(spacing: 8) {
                            Text("Then:")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                            Text(nextStep.instructions)
                                .font(.system(size: 12, design: .rounded))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        .padding(.top, 2)
                    }
                } else {
                    Text("Arrived at destination")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .shadow(color: .black.opacity(0.14), radius: 10, y: 4)
            .padding(.horizontal, 12)
            .padding(.top, 8)

            Spacer()

            // Bottom bar — ETA + end button
            HStack(spacing: 16) {
                if let eta = vm.navigationETA {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(eta, format: .dateTime.hour().minute())
                            .font(.system(size: 22, weight: .bold, design: .rounded))
                        Text("ETA")
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Button { vm.endNavigation() } label: {
                    Text("End")
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 24)
                        .padding(.vertical, 12)
                        .background(Color.red, in: Capsule())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .shadow(color: .black.opacity(0.12), radius: 10, y: -4)
            .padding(.horizontal, 12)
            .padding(.bottom, 8)
        }
    }

    private func maneuverIcon(for instruction: String) -> Image {
        let lower = instruction.lowercased()
        if lower.contains("left") { return Image(systemName: "arrow.turn.up.left") }
        if lower.contains("right") { return Image(systemName: "arrow.turn.up.right") }
        if lower.contains("u-turn") || lower.contains("uturn") { return Image(systemName: "arrow.uturn.left") }
        if lower.contains("merge") { return Image(systemName: "arrow.merge") }
        if lower.contains("exit") || lower.contains("ramp") { return Image(systemName: "arrow.turn.down.right") }
        if lower.contains("arrive") || lower.contains("destination") { return Image(systemName: "mappin.circle.fill") }
        return Image(systemName: "arrow.up")
    }
}

private struct LocationRow: View {
    let icon: String
    let iconColor: Color
    let placeholder: String
    let value: String?
    let palette: QuailThemePalette
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(iconColor)
                    .frame(width: 24)
                Text(value ?? placeholder)
                    .font(.system(size: 14, weight: value == nil ? .regular : .medium, design: .rounded))
                    .foregroundStyle(value == nil ? .secondary : palette.chromeIconForeground)
                    .lineLimit(1)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Location search sheet

private struct LocationSearchSheet: View {
    @ObservedObject var vm: RouteMapViewModel
    let palette: QuailThemePalette
    @StateObject private var store = SavedLocationsStore.shared
    @State private var query = ""

    var body: some View {
        VStack(spacing: 0) {
            Text(vm.searchTarget == .origin ? "Set Starting Location" : "Set Destination")
                .font(.system(size: 16, weight: .bold, design: .rounded))
                .padding(.top, 20)
                .padding(.bottom, 12)

            // Saved locations quick-pick
            if !store.locations.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(store.locations) { loc in
                            Button {
                                let coord = loc.coordinate
                                if vm.searchTarget == .origin {
                                    vm.originCoordinate = coord
                                    vm.originName = loc.name
                                } else {
                                    vm.destinationCoordinate = coord
                                    vm.destinationName = loc.name
                                }
                                vm.locationResults = []
                                vm.showingSearchSheet = false
                                // Trigger recalc via the same path as selectLocation
                                Task { @MainActor in
                                    if vm.originCoordinate != nil && vm.destinationCoordinate != nil {
                                        vm.triggerRecalculate()
                                    }
                                }
                            } label: {
                                HStack(spacing: 5) {
                                    Text(loc.emoji)
                                    Text(loc.name)
                                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                                }
                                .foregroundStyle(palette.chromeIconForeground)
                                .padding(.horizontal, 12).padding(.vertical, 7)
                                .background(palette.surface, in: Capsule())
                                .overlay(Capsule().stroke(palette.border, lineWidth: 1))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 16).padding(.bottom, 10)
                }
            }

            // Use current location option (for origin)
            if vm.searchTarget == .origin {
                Button {
                    vm.useCurrentLocationAsOrigin()
                    vm.showingSearchSheet = false
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "location.fill")
                            .foregroundStyle(.blue)
                            .frame(width: 28)
                        Text("Use Current Location")
                            .font(.system(size: 14, weight: .medium, design: .rounded))
                        Spacer()
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(Color.blue.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
            }

            // Search field
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search for a place...", text: $query)
                    .font(.system(size: 14, design: .rounded))
                    .autocorrectionDisabled()
                    .onChange(of: query) { _, q in vm.searchLocations(query: q) }
                if !query.isEmpty {
                    Button { query = ""; vm.locationResults = [] } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .padding(.horizontal, 16)
            .padding(.bottom, 8)

            if vm.isSearching {
                ProgressView().padding(.top, 20)
                Spacer()
            } else if vm.locationResults.isEmpty && !query.isEmpty {
                Text("No results found").foregroundStyle(.secondary).padding(.top, 20)
                Spacer()
            } else {
                List(vm.locationResults, id: \.self) { item in
                    Button {
                        vm.selectLocation(item)
                        vm.showingSearchSheet = false
                        query = ""
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.name ?? "Unknown")
                                .font(.system(size: 14, weight: .medium, design: .rounded))
                            if let subtitle = item.placemark.title {
                                Text(subtitle)
                                    .font(.system(size: 12, design: .rounded))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
                .listStyle(.plain)
            }
        }
    }
}

// MARK: - Detour picker sheet

private struct DetourPickerSheet: View {
    @ObservedObject var vm: RouteMapViewModel
    let palette: QuailThemePalette

    var body: some View {
        VStack(spacing: 0) {
            Text("Add a Stop")
                .font(.system(size: 16, weight: .bold, design: .rounded))
                .padding(.top, 20)
                .padding(.bottom, 4)
            Text("Only shows places along your route")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.bottom, 14)

            // Category picker
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(DetourCategory.allCases) { cat in
                        Button {
                            vm.selectedDetourCategory = cat
                            vm.searchDetours(category: cat)
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: cat.systemImage)
                                    .font(.system(size: 13, weight: .semibold))
                                Text(cat.label)
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                            }
                            .foregroundStyle(vm.selectedDetourCategory == cat ? .white : cat.color)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 7)
                            .background(
                                vm.selectedDetourCategory == cat ? cat.color : cat.color.opacity(0.12),
                                in: Capsule()
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 16)
            }
            .padding(.bottom, 12)

            Divider()

            if vm.isLoadingDetours {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Finding stops along your route…")
                        .font(.system(size: 13, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.detourResults.isEmpty && vm.selectedDetourCategory != nil {
                Text("No results found along your route.")
                    .font(.system(size: 13, design: .rounded))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(vm.detourResults) { candidate in
                    DetourResultRow(candidate: candidate, palette: palette) {
                        vm.addDetour(candidate)
                        vm.showingDetourPicker = false
                    }
                }
                .listStyle(.plain)
            }
        }
    }
}

private struct DetourResultRow: View {
    let candidate: DetourCandidate
    let palette: QuailThemePalette
    let onAdd: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: candidate.category.systemImage)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(candidate.category.color)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(candidate.name)
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .lineLimit(1)
                if let address = candidate.address {
                    Text(address)
                        .font(.system(size: 12, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("+\(formatDuration(candidate.addedSeconds))")
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .foregroundStyle(candidate.addedSeconds < 300 ? .green : candidate.addedSeconds < 600 ? .orange : .red)
                Text(formatDistance(candidate.distanceFromRoute))
                    .font(.system(size: 11, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            Button(action: onAdd) {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(.blue)
            }
            .buttonStyle(.plain)
        }
        .padding(.vertical, 4)
    }
}

// MARK: - View model

@MainActor
final class RouteMapViewModel: ObservableObject {
    @Published var cameraPosition: MapCameraPosition = .automatic
    @Published var userLocation: CLLocationCoordinate2D?
    @Published var originName: String = ""
    @Published var originCoordinate: CLLocationCoordinate2D?
    @Published var destinationName: String = ""
    @Published var destinationCoordinate: CLLocationCoordinate2D?
    @Published var activeRoute: MKRoute?
    @Published var alternativeRoutes: [MKRoute] = []
    @Published var routeSegments: [MKRoute] = []  // all legs when detours are active
    @Published var activeRouteIndex: Int = 0
    @Published var addedDetours: [DetourWaypoint] = []

    // Timing
    @Published var scheduleMode: ScheduleMode = .arriveBy
    @Published var scheduleTime: Date = Date().addingTimeInterval(3600)
    @Published var showingTimePicker = false

    // legacy alias
    var arriveBy: Date { scheduleTime }
    @Published var transportType: MKDirectionsTransportType = .automobile

    // Mode
    @Published var mapMode: MapPanelMode = .route

    // Route search
    @Published var showingSearchSheet = false
    @Published var searchTarget: SearchTarget = .destination
    @Published var locationResults: [MKMapItem] = []
    @Published var isSearching = false

    // Explore / place discovery
    @Published var exploreQuery = ""
    @Published var exploreCategory: ExploreCategory? = nil
    @Published var exploreResults: [MKMapItem] = []
    @Published var isExploring = false
    @Published var selectedPlace: MKMapItem? = nil

    // Traffic
    @Published var routeTraffic: TrafficCongestion = .unknown

    // Inline detours
    @Published var activeDetourCategories: Set<DetourCategory> = []
    @Published var inlineDetourResults: [String: [DetourCandidate]] = [:]
    @Published var loadingDetourCategories: Set<String> = []
    @Published var detourThreshold: Double = 1.0

    // Legacy (DetourPickerSheet still wired)
    @Published var showingDetourPicker = false
    @Published var selectedDetourCategory: DetourCategory?
    @Published var detourResults: [DetourCandidate] = []
    @Published var isLoadingDetours = false

    // Isochrone / travel-time heat map
    @Published var isochroneMode = false
    @Published var isochroneCenter: CLLocationCoordinate2D? = nil
    @Published var isochroneTransport: IsochroneTransport = .drive
    @Published var isochronePolygons: [(minutes: Int, coords: [CLLocationCoordinate2D])] = []
    @Published var isLoadingIsochrones = false
    @Published var walkingSpeedMPS: Double = 1.4

    enum IsochroneTransport: Hashable { case walk, drive }

    func setIsochroneCenter(_ coord: CLLocationCoordinate2D) {
        isochroneCenter = coord
        isochronePolygons = []
        Task { await fetchIsochronePolygons(center: coord) }
    }

    // Apple MKDirections-based isochrone: shoot routes in N compass directions,
    // interpolate along each route at each time interval, connect points into polygons.
    func fetchIsochronePolygons(center: CLLocationCoordinate2D) async {
        await MainActor.run { isLoadingIsochrones = true }

        let transport: MKDirectionsTransportType = isochroneTransport == .drive ? .automobile : .walking
        let bearingCount = 12
        let intervals = [10, 20, 30, 40, 50, 60]
        let maxDistMeters: Double = isochroneTransport == .drive ? 30_000 : 6_000

        // Each bearing returns an array of coords — one per interval
        var bearingResults: [[CLLocationCoordinate2D?]] = Array(repeating: Array(repeating: nil, count: intervals.count), count: bearingCount)

        await withTaskGroup(of: (Int, [CLLocationCoordinate2D?]).self) { group in
            for b in 0..<bearingCount {
                group.addTask { [self] in
                    let bearing = Double(b) * (360.0 / Double(bearingCount))
                    let probe = self.coordAt(origin: center, distanceMeters: maxDistMeters, bearingDeg: bearing)
                    let req = MKDirections.Request()
                    req.source = MKMapItem(placemark: MKPlacemark(coordinate: center))
                    req.destination = MKMapItem(placemark: MKPlacemark(coordinate: probe))
                    req.transportType = transport
                    guard let route = try? await MKDirections(request: req).calculate().routes.first else {
                        return (b, Array(repeating: nil, count: intervals.count))
                    }
                    let routeCoords = route.polyline.allCoordinates
                    let totalTime = route.expectedTravelTime
                    let totalDist = route.distance
                    var points: [CLLocationCoordinate2D?] = []
                    for minutes in intervals {
                        let t = Double(minutes * 60)
                        if t >= totalTime {
                            points.append(routeCoords.last)
                        } else {
                            points.append(self.interpolate(coords: routeCoords, totalDist: totalDist, totalTime: totalTime, atTime: t))
                        }
                    }
                    return (b, points)
                }
            }
            for await (b, pts) in group { bearingResults[b] = pts }
        }

        // Build one polygon per interval from the bearing endpoints
        var results: [(minutes: Int, coords: [CLLocationCoordinate2D])] = []
        for (idx, minutes) in intervals.enumerated() {
            let ring = (0..<bearingCount).compactMap { bearingResults[$0][idx] }
            if ring.count >= 3 { results.append((minutes: minutes, coords: ring)) }
        }

        await MainActor.run {
            isochronePolygons = results.sorted { $0.minutes > $1.minutes }
            isLoadingIsochrones = false
        }
    }

    nonisolated private func coordAt(origin: CLLocationCoordinate2D, distanceMeters: Double, bearingDeg: Double) -> CLLocationCoordinate2D {
        let R = 6_371_000.0
        let lat1 = origin.latitude * .pi / 180
        let lon1 = origin.longitude * .pi / 180
        let brng = bearingDeg * .pi / 180
        let lat2 = asin(sin(lat1) * cos(distanceMeters/R) + cos(lat1) * sin(distanceMeters/R) * cos(brng))
        let lon2 = lon1 + atan2(sin(brng) * sin(distanceMeters/R) * cos(lat1), cos(distanceMeters/R) - sin(lat1) * sin(lat2))
        return CLLocationCoordinate2D(latitude: lat2 * 180 / .pi, longitude: lon2 * 180 / .pi)
    }

    nonisolated private func interpolate(coords: [CLLocationCoordinate2D], totalDist: Double, totalTime: Double, atTime t: Double) -> CLLocationCoordinate2D? {
        guard coords.count > 1, totalDist > 0 else { return coords.first }
        var elapsed = 0.0
        for i in 1..<coords.count {
            let a = CLLocation(latitude: coords[i-1].latitude, longitude: coords[i-1].longitude)
            let b = CLLocation(latitude: coords[i].latitude, longitude: coords[i].longitude)
            let segDist = a.distance(from: b)
            let segTime = (segDist / totalDist) * totalTime
            if elapsed + segTime >= t {
                let frac = (t - elapsed) / max(segTime, 0.001)
                return CLLocationCoordinate2D(
                    latitude:  coords[i-1].latitude  + frac * (coords[i].latitude  - coords[i-1].latitude),
                    longitude: coords[i-1].longitude + frac * (coords[i].longitude - coords[i-1].longitude)
                )
            }
            elapsed += segTime
        }
        return coords.last
    }

    func fetchWalkingSpeedFromHealth() {
        guard HKHealthStore.isHealthDataAvailable(),
              let type = HKQuantityType.quantityType(forIdentifier: .walkingSpeed) else { return }
        let hkStore = HKHealthStore()
        hkStore.requestAuthorization(toShare: [], read: [type]) { [weak self] (granted: Bool, _: Error?) in
            guard granted else { return }
            let query = HKStatisticsQuery(quantityType: type, quantitySamplePredicate: nil, options: .discreteAverage) { [weak self] (_: HKStatisticsQuery, stats: HKStatistics?, _: Error?) in
                let mps = stats?.averageQuantity()?.doubleValue(for: HKUnit(from: "m/s"))
                Task { @MainActor [weak self] in
                    if let mps { self?.walkingSpeedMPS = mps }
                }
            }
            hkStore.execute(query)
        }
    }

    func toggleIsochroneMode() {
        isochroneMode.toggle()
        if !isochroneMode {
            isochroneCenter = nil
            isochronePolygons = []
        } else {
            fetchWalkingSpeedFromHealth()
        }
    }

    // Navigation
    @Published var isNavigating = false
    @Published var currentStepIndex = 0
    @Published var distanceToNextStep: Double = 0
    @Published var navigationETA: Date?
    @Published var completedTripMiles: Double? = nil
    @Published var completedTripDestination: String = ""
    private var navigationStartedAt: Date = Date()

    private var locationDelegate: LocationDelegate?
    private let locationManager = CLLocationManager()
    private var searchTask: Task<Void, Never>?
    private var recalculateTask: Task<Void, Never>?
    private var baseRouteTravelTime: Double = 0
    private let speechSynth = AVSpeechSynthesizer()
    private var lastSpokenStepIndex = -1

    enum SearchTarget { case origin, destination }

    func departBy(for route: MKRoute) -> Date {
        if scheduleMode == .leaveAt { return scheduleTime }
        return scheduleTime.addingTimeInterval(-route.expectedTravelTime)
    }

    func arriveAt(for route: MKRoute) -> Date {
        if scheduleMode == .arriveBy { return scheduleTime }
        return scheduleTime.addingTimeInterval(route.expectedTravelTime)
    }

    init() {
        let delegate = LocationDelegate { [weak self] location in
            Task { @MainActor in
                guard let self else { return }
                self.userLocation = location.coordinate
                if self.originCoordinate == nil, self.originName.isEmpty {
                    self.cameraPosition = .region(MKCoordinateRegion(center: location.coordinate, latitudinalMeters: 5000, longitudinalMeters: 5000))
                }
                if self.isNavigating {
                    self.updateNavigationProgress(location: location)
                }
            }
        }
        locationDelegate = delegate
        locationManager.delegate = delegate
        locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
    }

    func requestLocation() {
        locationManager.requestWhenInUseAuthorization()
        locationManager.requestLocation()
    }

    func useCurrentLocationAsOrigin() {
        guard let loc = userLocation else { return }
        originCoordinate = loc
        originName = "Current Location"
        recalculateRoute()
    }

    func swapLocations() {
        let tmpName = originName
        let tmpCoord = originCoordinate
        originName = destinationName
        originCoordinate = destinationCoordinate
        destinationName = tmpName
        destinationCoordinate = tmpCoord
        recalculateRoute()
    }

    func searchLocations(query: String) {
        searchTask?.cancel()
        guard query.count >= 2 else { locationResults = []; return }
        isSearching = true
        searchTask = Task {
            let req = MKLocalSearch.Request()
            req.naturalLanguageQuery = query
            if let region = regionForSearch() { req.region = region }
            do {
                let results = try await MKLocalSearch(request: req).start()
                if !Task.isCancelled {
                    locationResults = results.mapItems
                    isSearching = false
                }
            } catch {
                if !Task.isCancelled {
                    locationResults = []
                    isSearching = false
                }
            }
        }
    }

    func selectLocation(_ item: MKMapItem) {
        let coord = item.placemark.coordinate
        let name = item.name ?? item.placemark.title ?? "Unknown"
        if searchTarget == .origin {
            originCoordinate = coord
            originName = name
        } else {
            destinationCoordinate = coord
            destinationName = name
        }
        locationResults = []
        recalculateRoute()
    }

    func searchDetours(category: DetourCategory) {
        guard let origin = currentOriginCoordinate(), let destination = destinationCoordinate else { return }
        isLoadingDetours = true
        detourResults = []
        Task {
            let midLat = (origin.latitude + destination.latitude) / 2
            let midLon = (origin.longitude + destination.longitude) / 2
            let midpoint = CLLocationCoordinate2D(latitude: midLat, longitude: midLon)
            let latDelta = abs(destination.latitude - origin.latitude) * 1.3
            let lonDelta = abs(destination.longitude - origin.longitude) * 1.3
            let searchRegion = MKCoordinateRegion(
                center: midpoint,
                span: MKCoordinateSpan(latitudeDelta: max(latDelta, 0.05), longitudeDelta: max(lonDelta, 0.05))
            )

            let req = MKLocalSearch.Request()
            req.naturalLanguageQuery = category.searchQuery
            req.region = searchRegion
            req.resultTypes = .pointOfInterest

            guard let searchResults = try? await MKLocalSearch(request: req).start() else {
                isLoadingDetours = false
                return
            }

            // Filter to items roughly in the direction of travel and score by added time
            let candidates = await rankDetours(
                items: searchResults.mapItems,
                origin: origin,
                destination: destination,
                category: category
            )
            detourResults = candidates
            isLoadingDetours = false
        }
    }

    func addDetour(_ candidate: DetourCandidate) {
        let waypoint = DetourWaypoint(
            id: UUID(),
            name: candidate.name,
            coordinate: candidate.coordinate,
            category: candidate.category
        )
        addedDetours.append(waypoint)
        recalculateRoute()
    }

    func removeDetour(_ waypoint: DetourWaypoint) {
        addedDetours.removeAll { $0.id == waypoint.id }
        recalculateRoute()
    }

    func openInMaps() {
        var waypoints: [MKMapItem] = []
        if let origin = currentOriginCoordinate() {
            let placemark = MKPlacemark(coordinate: origin)
            waypoints.append(MKMapItem(placemark: placemark))
        }
        for detour in addedDetours {
            let placemark = MKPlacemark(coordinate: detour.coordinate)
            let item = MKMapItem(placemark: placemark)
            item.name = detour.name
            waypoints.append(item)
        }
        if let dest = destinationCoordinate {
            let placemark = MKPlacemark(coordinate: dest)
            let item = MKMapItem(placemark: placemark)
            item.name = destinationName
            waypoints.append(item)
        }
        guard !waypoints.isEmpty else { return }
        let options: [String: Any] = [MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving]
        MKMapItem.openMaps(with: waypoints, launchOptions: options)
    }

    // MARK: - Private

    private func currentOriginCoordinate() -> CLLocationCoordinate2D? {
        originCoordinate ?? userLocation
    }

    func searchPlaces(query: String) {
        searchTask?.cancel()
        guard !query.trimmingCharacters(in: .whitespaces).isEmpty else { exploreResults = []; return }
        isExploring = true
        searchTask = Task {
            let req = MKLocalSearch.Request()
            req.naturalLanguageQuery = query
            if let region = regionForSearch() { req.region = region }
            req.resultTypes = .pointOfInterest
            if let results = try? await MKLocalSearch(request: req).start(), !Task.isCancelled {
                exploreResults = results.mapItems
                isExploring = false
                fitExploreResults()
            } else if !Task.isCancelled {
                isExploring = false
            }
        }
    }

    func searchCategory(_ cat: ExploreCategory) {
        exploreCategory = cat
        exploreQuery = ""
        searchPlaces(query: cat.searchQuery)
    }

    func clearExplore() {
        exploreResults = []
        exploreQuery = ""
        exploreCategory = nil
        selectedPlace = nil
    }

    func routeToPlace(_ item: MKMapItem) {
        destinationCoordinate = item.placemark.coordinate
        destinationName = item.name ?? item.placemark.title ?? "Destination"
        selectedPlace = nil
        mapMode = .route
        recalculateRoute()
    }

    private func fitExploreResults() {
        guard !exploreResults.isEmpty else { return }
        let coords = exploreResults.map(\.placemark.coordinate)
        let lats = coords.map(\.latitude)
        let lons = coords.map(\.longitude)
        let center = CLLocationCoordinate2D(
            latitude: (lats.min()! + lats.max()!) / 2,
            longitude: (lons.min()! + lons.max()!) / 2
        )
        let span = MKCoordinateSpan(
            latitudeDelta: (lats.max()! - lats.min()!) * 1.4 + 0.02,
            longitudeDelta: (lons.max()! - lons.min()!) * 1.4 + 0.02
        )
        cameraPosition = .region(MKCoordinateRegion(center: center, span: span))
    }

    func triggerRecalculate() {
        recalculateTask?.cancel()
        recalculateTask = Task {
            try? await Task.sleep(for: .milliseconds(600))
            guard !Task.isCancelled else { return }
            recalculateRoute()
        }
    }

    func startNavigation() {
        guard activeRoute != nil else { return }
        isNavigating = true
        currentStepIndex = 0
        lastSpokenStepIndex = -1
        navigationStartedAt = Date()
        completedTripMiles = nil
        locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
        locationManager.startUpdatingLocation()
        updateETA()
    }

    func endNavigation() {
        let endedAt = Date()
        isNavigating = false
        speechSynth.stopSpeaking(at: .immediate)
        locationManager.stopUpdatingLocation()
        locationManager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        locationManager.requestLocation()

        guard let route = activeRoute else { return }
        let miles = route.distance * 0.000621371
        completedTripMiles = miles
        completedTripDestination = destinationName
        let origin = originName
        let dest = destinationName
        let dur = Int(endedAt.timeIntervalSince(navigationStartedAt))
        let type = transportType == .automobile ? "automobile" : "transit"
        let start = navigationStartedAt

        Task {
            try? await QuailCashAPI.shared.logMapTrip(
                originName: origin,
                destinationName: dest,
                distanceMiles: miles,
                durationSeconds: dur,
                transportType: type,
                startedAt: start,
                endedAt: endedAt
            )
        }
    }

    func confirmOdometerUpdate() {
        guard let miles = completedTripMiles else { return }
        let newMileage = VehicleStore.shared.profile.currentMileage + Int(miles.rounded())
        VehicleStore.shared.profile.currentMileage = newMileage
        VehicleStore.shared.save()
        Task { try? await QuailCashAPI.shared.updateVehicleMileage(newMileage) }
        completedTripMiles = nil
    }

    private func updateNavigationProgress(location: CLLocation) {
        guard let route = activeRoute, currentStepIndex < route.steps.count else { return }
        let step = route.steps[currentStepIndex]

        // Distance to end of current step
        let stepPoints = step.polyline.points()
        let lastPoint = stepPoints[step.polyline.pointCount - 1]
        let stepEndCoord = lastPoint.coordinate
        let stepEndLoc = CLLocation(latitude: stepEndCoord.latitude, longitude: stepEndCoord.longitude)
        distanceToNextStep = location.distance(from: stepEndLoc)

        // Speak instruction on first arrival at this step
        if lastSpokenStepIndex != currentStepIndex, !step.instructions.isEmpty {
            let utterance = AVSpeechUtterance(string: step.instructions)
            utterance.rate = 0.52
            speechSynth.speak(utterance)
            lastSpokenStepIndex = currentStepIndex
        }

        // Advance step when within 30m of endpoint
        if distanceToNextStep < 30, currentStepIndex + 1 < route.steps.count {
            currentStepIndex += 1
        }

        // Follow camera
        let heading = location.course >= 0 ? location.course : 0
        let offset = 0.0008
        let rad = heading * .pi / 180
        let aheadLat = location.coordinate.latitude + offset * cos(rad)
        let aheadLon = location.coordinate.longitude + offset * sin(rad)
        cameraPosition = .region(MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: aheadLat, longitude: aheadLon),
            span: MKCoordinateSpan(latitudeDelta: 0.006, longitudeDelta: 0.006)
        ))

        updateETA()
    }

    private func updateETA() {
        guard let route = activeRoute, route.steps.count > 0 else { return }
        let stepsDone = Double(currentStepIndex)
        let totalSteps = Double(route.steps.count)
        let fraction = 1.0 - (stepsDone / totalSteps)
        let secondsRemaining = route.expectedTravelTime * max(0.0, fraction)
        navigationETA = Date().addingTimeInterval(max(10, secondsRemaining))
    }

    func selectRoute(index: Int) {
        guard alternativeRoutes.indices.contains(index) else { return }
        activeRouteIndex = index
        activeRoute = alternativeRoutes[index]
        routeSegments = [alternativeRoutes[index]]
    }

    func toggleDetourCategory(_ cat: DetourCategory) {
        if activeDetourCategories.contains(cat) {
            activeDetourCategories.remove(cat)
            inlineDetourResults.removeValue(forKey: cat.rawValue)
        } else {
            activeDetourCategories.insert(cat)
            detourThreshold = 1.0
            searchDetoursInline(category: cat)
        }
    }

    func expandDetourThreshold(for cat: DetourCategory) {
        detourThreshold = min(detourThreshold * 1.5, 5.0)
        searchDetoursInline(category: cat)
    }

    private func searchDetoursInline(category: DetourCategory) {
        guard let origin = currentOriginCoordinate(), let destination = destinationCoordinate else { return }
        let key = category.rawValue
        loadingDetourCategories.insert(key)
        inlineDetourResults.removeValue(forKey: key)
        Task {
            let midLat = (origin.latitude + destination.latitude) / 2
            let midLon = (origin.longitude + destination.longitude) / 2
            let latDelta = abs(destination.latitude - origin.latitude) * 1.3 * detourThreshold
            let lonDelta = abs(destination.longitude - origin.longitude) * 1.3 * detourThreshold
            let req = MKLocalSearch.Request()
            req.naturalLanguageQuery = category.searchQuery
            req.region = MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: midLat, longitude: midLon),
                span: MKCoordinateSpan(
                    latitudeDelta: max(latDelta, 0.05 * detourThreshold),
                    longitudeDelta: max(lonDelta, 0.05 * detourThreshold)
                )
            )
            req.resultTypes = .pointOfInterest
            guard let results = try? await MKLocalSearch(request: req).start() else {
                loadingDetourCategories.remove(key); return
            }
            let candidates = await rankDetours(items: results.mapItems, origin: origin, destination: destination, category: category)
            inlineDetourResults[key] = Array(candidates.prefix(5))
            loadingDetourCategories.remove(key)
        }
    }

    private func recalculateRoute() {
        guard let origin = currentOriginCoordinate(), let destination = destinationCoordinate else { return }
        Task {
            if addedDetours.isEmpty {
                let req = MKDirections.Request()
                req.source = MKMapItem(placemark: MKPlacemark(coordinate: origin))
                req.destination = MKMapItem(placemark: MKPlacemark(coordinate: destination))
                req.transportType = transportType
                req.requestsAlternateRoutes = (transportType == .automobile)
                if scheduleMode == .arriveBy {
                    req.arrivalDate = scheduleTime
                } else {
                    req.departureDate = scheduleTime
                }
                if let result = try? await MKDirections(request: req).calculate() {
                    let routes = Array(result.routes.sorted { $0.expectedTravelTime < $1.expectedTravelTime }.prefix(3))
                    alternativeRoutes = routes
                    routeSegments = routes.first.map { [$0] } ?? []
                    activeRouteIndex = 0
                    activeRoute = routes.first
                    baseRouteTravelTime = routes.first?.expectedTravelTime ?? 0
                    // Fetch traffic at route midpoint
                    let midLat = (origin.latitude + destination.latitude) / 2
                    let midLon = (origin.longitude + destination.longitude) / 2
                    routeTraffic = await TomTomService.shared.fetchTrafficCongestion(
                        at: CLLocationCoordinate2D(latitude: midLat, longitude: midLon)
                    )
                }
            } else {
                let coords = [origin] + addedDetours.map(\.coordinate) + [destination]
                var segments: [MKRoute] = []
                for i in 0..<(coords.count - 1) {
                    let req = MKDirections.Request()
                    req.source = MKMapItem(placemark: MKPlacemark(coordinate: coords[i]))
                    req.destination = MKMapItem(placemark: MKPlacemark(coordinate: coords[i + 1]))
                    req.transportType = transportType
                    if let result = try? await MKDirections(request: req).calculate(),
                       let route = result.routes.first { segments.append(route) }
                }
                if let first = segments.first {
                    routeSegments = segments
                    alternativeRoutes = [first]
                    activeRouteIndex = 0
                    activeRoute = first
                    baseRouteTravelTime = segments.reduce(0) { $0 + $1.expectedTravelTime }
                }
            }
            // Zoom to fit
            if let dest = destinationCoordinate {
                let center = CLLocationCoordinate2D(
                    latitude: (origin.latitude + dest.latitude) / 2,
                    longitude: (origin.longitude + dest.longitude) / 2
                )
                cameraPosition = .region(MKCoordinateRegion(
                    center: center,
                    span: MKCoordinateSpan(
                        latitudeDelta: abs(origin.latitude - dest.latitude) * 1.5 + 0.02,
                        longitudeDelta: abs(origin.longitude - dest.longitude) * 1.5 + 0.02
                    )
                ))
            }
        }
    }

    private func rankDetours(
        items: [MKMapItem],
        origin: CLLocationCoordinate2D,
        destination: CLLocationCoordinate2D,
        category: DetourCategory
    ) async -> [DetourCandidate] {
        // Get base route time
        let baseReq = MKDirections.Request()
        baseReq.source = MKMapItem(placemark: MKPlacemark(coordinate: origin))
        baseReq.destination = MKMapItem(placemark: MKPlacemark(coordinate: destination))
        baseReq.transportType = .automobile
        let baseTime = (try? await MKDirections(request: baseReq).calculate())?.routes.first?.expectedTravelTime ?? 0

        // Filter: drop items that are more than 20% off to the side using bearing
        let routeBearing = bearing(from: origin, to: destination)
        let filtered = items.filter { item in
            let coord = item.placemark.coordinate
            let b = bearing(from: origin, to: coord)
            let diff = abs(angleDiff(b, routeBearing))
            return diff < 90  // within 90° of direction of travel
        }

        // Score top 15 by added time
        var candidates: [DetourCandidate] = []
        for item in filtered.prefix(15) {
            let coord = item.placemark.coordinate
            let req1 = MKDirections.Request()
            req1.source = MKMapItem(placemark: MKPlacemark(coordinate: origin))
            req1.destination = MKMapItem(placemark: MKPlacemark(coordinate: coord))
            req1.transportType = .automobile

            let req2 = MKDirections.Request()
            req2.source = MKMapItem(placemark: MKPlacemark(coordinate: coord))
            req2.destination = MKMapItem(placemark: MKPlacemark(coordinate: destination))
            req2.transportType = .automobile

            async let t1Result = MKDirections(request: req1).calculate()
            async let t2Result = MKDirections(request: req2).calculate()

            guard let r1 = try? await t1Result, let r2 = try? await t2Result,
                  let leg1 = r1.routes.first, let leg2 = r2.routes.first else { continue }

            let detourTime = leg1.expectedTravelTime + leg2.expectedTravelTime
            let addedTime = max(0, detourTime - baseTime)

            // Reject if adds more than 50% of base route time (hard backtrack)
            if baseTime > 0 && addedTime > baseTime * 1.5 { continue }

            let distFromRoute = distanceFromSegment(
                point: coord, segStart: origin, segEnd: destination
            )

            candidates.append(DetourCandidate(
                id: UUID(),
                name: item.name ?? "Unknown",
                address: item.placemark.title,
                coordinate: coord,
                category: category,
                addedSeconds: addedTime,
                distanceFromRoute: distFromRoute
            ))
        }

        return candidates.sorted { $0.addedSeconds < $1.addedSeconds }
    }

    private func regionForSearch() -> MKCoordinateRegion? {
        if let dest = destinationCoordinate { return MKCoordinateRegion(center: dest, latitudinalMeters: 50000, longitudinalMeters: 50000) }
        if let origin = currentOriginCoordinate() { return MKCoordinateRegion(center: origin, latitudinalMeters: 50000, longitudinalMeters: 50000) }
        return nil
    }

    private func bearing(from: CLLocationCoordinate2D, to: CLLocationCoordinate2D) -> Double {
        let lat1 = from.latitude * .pi / 180
        let lat2 = to.latitude * .pi / 180
        let dLon = (to.longitude - from.longitude) * .pi / 180
        let y = sin(dLon) * cos(lat2)
        let x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dLon)
        return atan2(y, x) * 180 / .pi
    }

    private func angleDiff(_ a: Double, _ b: Double) -> Double {
        var d = a - b
        while d > 180 { d -= 360 }
        while d < -180 { d += 360 }
        return d
    }

    private func distanceFromSegment(
        point: CLLocationCoordinate2D,
        segStart: CLLocationCoordinate2D,
        segEnd: CLLocationCoordinate2D
    ) -> Double {
        let p = CLLocation(latitude: point.latitude, longitude: point.longitude)
        let a = CLLocation(latitude: segStart.latitude, longitude: segStart.longitude)
        let b = CLLocation(latitude: segEnd.latitude, longitude: segEnd.longitude)
        let ab = a.distance(from: b)
        guard ab > 0 else { return p.distance(from: a) }
        let ap = a.distance(from: p)
        let bp = b.distance(from: p)
        let t = ((ap * ap - bp * bp + ab * ab) / (2 * ab)).clamped(to: 0...ab)
        let closest = CLLocation(
            latitude: segStart.latitude + (segEnd.latitude - segStart.latitude) * (t / ab),
            longitude: segStart.longitude + (segEnd.longitude - segStart.longitude) * (t / ab)
        )
        return p.distance(from: closest)
    }

}

// MARK: - Location delegate helper

private final class LocationDelegate: NSObject, CLLocationManagerDelegate {
    let onLocation: (CLLocation) -> Void
    init(onLocation: @escaping (CLLocation) -> Void) {
        self.onLocation = onLocation
    }
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        onLocation(loc)
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {}
}

// MARK: - TomTom

private let tomTomKey = "6jVSiahwOxu2umw4wUNbYKWPcgomy23P"

enum TrafficCongestion: Equatable {
    case light, moderate, heavy, unknown
    var label: String {
        switch self { case .light: return "Light traffic"; case .moderate: return "Moderate"; case .heavy: return "Heavy traffic"; case .unknown: return "Traffic" }
    }
    var color: Color {
        switch self { case .light: return .green; case .moderate: return .orange; case .heavy: return .red; case .unknown: return .secondary }
    }
    var icon: String {
        switch self { case .light: return "checkmark.circle.fill"; case .moderate: return "exclamationmark.circle.fill"; case .heavy: return "xmark.circle.fill"; case .unknown: return "circle.dotted" }
    }
}

@MainActor
final class TomTomService {
    static let shared = TomTomService()

    func fetchTrafficCongestion(at coord: CLLocationCoordinate2D) async -> TrafficCongestion {
        let urlStr = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json?key=\(tomTomKey)&point=\(coord.latitude),\(coord.longitude)&unit=mph"
        guard let url = URL(string: urlStr),
              let (data, _) = try? await URLSession.shared.data(from: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let flow = json["flowSegmentData"] as? [String: Any],
              let current = flow["currentSpeed"] as? Double,
              let free = flow["freeFlowSpeed"] as? Double,
              free > 0 else { return .unknown }
        let ratio = current / free
        if ratio > 0.75 { return .light }
        if ratio > 0.4 { return .moderate }
        return .heavy
    }
}

// MARK: - Models

enum MapPanelMode { case route, explore }
enum ScheduleMode { case leaveAt, arriveBy }

enum ExploreCategory: String, CaseIterable, Identifiable {
    case food, coffee, grocery, shopping, pharmacy, gas, hotel, entertainment, bar, bakery

    var id: String { rawValue }
    var label: String {
        switch self {
        case .food: return "Food"
        case .coffee: return "Coffee"
        case .grocery: return "Grocery"
        case .shopping: return "Shopping"
        case .pharmacy: return "Pharmacy"
        case .gas: return "Gas"
        case .hotel: return "Hotel"
        case .entertainment: return "Entertainment"
        case .bar: return "Bar"
        case .bakery: return "Bakery"
        }
    }
    var icon: String {
        switch self {
        case .food: return "fork.knife"
        case .coffee: return "cup.and.saucer.fill"
        case .grocery: return "cart.fill"
        case .shopping: return "bag.fill"
        case .pharmacy: return "cross.fill"
        case .gas: return "fuelpump.fill"
        case .hotel: return "bed.double.fill"
        case .entertainment: return "theatermasks.fill"
        case .bar: return "wineglass.fill"
        case .bakery: return "birthday.cake.fill"
        }
    }
    var color: Color {
        switch self {
        case .food: return .red
        case .coffee: return .brown
        case .grocery: return .green
        case .shopping: return .pink
        case .pharmacy: return .teal
        case .gas: return .orange
        case .hotel: return .indigo
        case .entertainment: return .purple
        case .bar: return .yellow
        case .bakery: return .orange
        }
    }
    var searchQuery: String {
        switch self {
        case .food: return "restaurant"
        case .coffee: return "coffee"
        case .grocery: return "grocery store"
        case .shopping: return "shopping"
        case .pharmacy: return "pharmacy"
        case .gas: return "gas station"
        case .hotel: return "hotel"
        case .entertainment: return "entertainment"
        case .bar: return "bar"
        case .bakery: return "bakery"
        }
    }
}

struct DetourWaypoint: Identifiable {
    let id: UUID
    let name: String
    let coordinate: CLLocationCoordinate2D
    let category: DetourCategory
}

struct DetourCandidate: Identifiable {
    let id: UUID
    let name: String
    let address: String?
    let coordinate: CLLocationCoordinate2D
    let category: DetourCategory
    let addedSeconds: Double
    let distanceFromRoute: Double
}

enum DetourCategory: String, CaseIterable, Identifiable {
    case gas, food, coffee, grocery, charging

    var id: String { rawValue }
    var label: String {
        switch self {
        case .gas: return "Gas"
        case .food: return "Food"
        case .coffee: return "Coffee"
        case .grocery: return "Grocery"
        case .charging: return "EV Charging"
        }
    }
    var systemImage: String {
        switch self {
        case .gas: return "fuelpump.fill"
        case .food: return "fork.knife"
        case .coffee: return "cup.and.saucer.fill"
        case .grocery: return "cart.fill"
        case .charging: return "bolt.car.fill"
        }
    }
    var color: Color {
        switch self {
        case .gas: return .orange
        case .food: return .red
        case .coffee: return .brown
        case .grocery: return .green
        case .charging: return .blue
        }
    }
    var searchQuery: String {
        switch self {
        case .gas: return "gas station"
        case .food: return "restaurant"
        case .coffee: return "coffee"
        case .grocery: return "grocery store"
        case .charging: return "EV charging station"
        }
    }
}

// MARK: - Saved locations model

struct SavedMapLocation: Codable, Identifiable {
    let id: UUID
    var name: String
    var emoji: String
    var latitude: Double
    var longitude: Double

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}

final class SavedLocationsStore: ObservableObject {
    static let shared = SavedLocationsStore()
    @Published var locations: [SavedMapLocation] = []

    private let key = "quail.map.savedLocations"

    init() { load() }

    func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([SavedMapLocation].self, from: data)
        else { return }
        locations = decoded
    }

    func save() {
        if let data = try? JSONEncoder().encode(locations) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    func add(_ loc: SavedMapLocation) {
        locations.append(loc)
        save()
    }

    func delete(at offsets: IndexSet) {
        locations.remove(atOffsets: offsets)
        save()
    }

    func update(_ loc: SavedMapLocation) {
        if let i = locations.firstIndex(where: { $0.id == loc.id }) {
            locations[i] = loc
            save()
        }
    }
}

// MARK: - Map settings page

struct MapSettingsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var store = SavedLocationsStore.shared
    @State private var showingAdd = false
    @State private var editingLocation: SavedMapLocation?

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: "Map Settings",
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            showsStandaloneBar: true,
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { navigator.show(.notifications) }
        ) {
            AppPageScroll {
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Text("Saved Locations")
                            .font(.system(size: 13, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .textCase(.uppercase)
                        Spacer()
                        Button {
                            showingAdd = true
                        } label: {
                            Image(systemName: "plus.circle.fill")
                                .font(.system(size: 20, weight: .semibold))
                                .foregroundStyle(palette.primaryButton)
                        }
                        .buttonStyle(.plain)
                    }

                    if store.locations.isEmpty {
                        Text("No saved locations yet. Add home, work, or any frequent destination for quick access.")
                            .font(.system(size: 13, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.vertical, 8)
                    } else {
                        VStack(spacing: 0) {
                            ForEach(store.locations) { loc in
                                HStack(spacing: 12) {
                                    Text(loc.emoji)
                                        .font(.system(size: 22))
                                        .frame(width: 36)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(loc.name)
                                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                                        Text(String(format: "%.4f, %.4f", loc.latitude, loc.longitude))
                                            .font(.system(size: 11, design: .rounded))
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Button {
                                        editingLocation = loc
                                    } label: {
                                        Image(systemName: "pencil")
                                            .font(.system(size: 14, weight: .medium))
                                            .foregroundStyle(.secondary)
                                    }
                                    .buttonStyle(.plain)
                                }
                                .padding(.vertical, 12)
                                .padding(.horizontal, 14)
                                if loc.id != store.locations.last?.id {
                                    Divider().padding(.leading, 62)
                                }
                            }
                            .onDelete { store.delete(at: $0) }
                        }
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
                    }
                }
            }
        }
        .sheet(isPresented: $showingAdd) {
            AddSavedLocationSheet(palette: QuailTheme.palette(for: themeSelection)) { newLoc in
                store.add(newLoc)
            }
            .presentationDetents([.medium])
        }
        .sheet(item: $editingLocation) { loc in
            EditSavedLocationSheet(location: loc, palette: QuailTheme.palette(for: themeSelection)) { updated in
                store.update(updated)
            }
            .presentationDetents([.medium])
        }
    }
}

fileprivate struct AddSavedLocationSheet: View {
    let palette: QuailThemePalette
    let onSave: (SavedMapLocation) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var emoji = "📍"
    @State private var query = ""
    @State private var results: [MKMapItem] = []
    @State private var selected: MKMapItem?
    @State private var isSearching = false

    var body: some View {
        VStack(spacing: 0) {
            Text("Add Saved Location")
                .font(.system(size: 16, weight: .bold, design: .rounded))
                .padding(.top, 20).padding(.bottom, 16)

            VStack(spacing: 12) {
                HStack(spacing: 10) {
                    TextField("Emoji", text: $emoji)
                        .font(.system(size: 22))
                        .multilineTextAlignment(.center)
                        .frame(width: 48)
                        .padding(8)
                        .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))
                    TextField("Name (e.g. Home, Work)", text: $name)
                        .font(.system(size: 14, design: .rounded))
                        .padding(.horizontal, 12).padding(.vertical, 10)
                        .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))
                }

                if let sel = selected {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                        Text(sel.name ?? "Selected")
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                        Spacer()
                        Button { selected = nil; query = "" } label: {
                            Image(systemName: "xmark.circle").foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(Color.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                } else {
                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                        TextField("Search for a place…", text: $query)
                            .font(.system(size: 14, design: .rounded))
                            .onChange(of: query) { _, q in
                                guard q.count >= 2 else { results = []; return }
                                Task {
                                    let req = MKLocalSearch.Request()
                                    req.naturalLanguageQuery = q
                                    if let items = try? await MKLocalSearch(request: req).start() {
                                        results = items.mapItems
                                    }
                                }
                            }
                    }
                    .padding(.horizontal, 12).padding(.vertical, 10)
                    .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))

                    if !results.isEmpty {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 0) {
                                ForEach(results.prefix(5), id: \.self) { item in
                                    Button {
                                        selected = item
                                        if name.isEmpty { name = item.name ?? "" }
                                        results = []
                                    } label: {
                                        HStack {
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(item.name ?? "").font(.system(size: 13, weight: .medium, design: .rounded))
                                                if let title = item.placemark.title {
                                                    Text(title).font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary).lineLimit(1)
                                                }
                                            }
                                            Spacer()
                                        }
                                        .padding(.horizontal, 12).padding(.vertical, 8)
                                    }
                                    .buttonStyle(.plain)
                                    Divider().padding(.leading, 12)
                                }
                            }
                        }
                        .frame(maxHeight: 160)
                        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
            .padding(.horizontal, 16)

            Spacer()

            Button {
                guard let sel = selected, !name.isEmpty else { return }
                let loc = SavedMapLocation(
                    id: UUID(),
                    name: name,
                    emoji: String(emoji.prefix(2)),
                    latitude: sel.placemark.coordinate.latitude,
                    longitude: sel.placemark.coordinate.longitude
                )
                onSave(loc)
                dismiss()
            } label: {
                Text("Save Location")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .foregroundStyle(palette.primaryButtonText)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(selected != nil && !name.isEmpty ? palette.primaryButton : palette.border, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            .disabled(selected == nil || name.isEmpty)
            .padding(.horizontal, 16).padding(.bottom, 20)
        }
    }
}

fileprivate struct EditSavedLocationSheet: View {
    let location: SavedMapLocation
    let palette: QuailThemePalette
    let onSave: (SavedMapLocation) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name: String
    @State private var emoji: String

    init(location: SavedMapLocation, palette: QuailThemePalette, onSave: @escaping (SavedMapLocation) -> Void) {
        self.location = location
        self.palette = palette
        self.onSave = onSave
        _name = State(initialValue: location.name)
        _emoji = State(initialValue: location.emoji)
    }

    var body: some View {
        VStack(spacing: 16) {
            Text("Edit Location").font(.system(size: 16, weight: .bold, design: .rounded)).padding(.top, 20)
            HStack(spacing: 10) {
                TextField("Emoji", text: $emoji)
                    .font(.system(size: 22)).multilineTextAlignment(.center)
                    .frame(width: 48).padding(8)
                    .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))
                TextField("Name", text: $name)
                    .font(.system(size: 14, design: .rounded))
                    .padding(.horizontal, 12).padding(.vertical, 10)
                    .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))
            }
            .padding(.horizontal, 16)
            Text(String(format: "%.4f, %.4f", location.latitude, location.longitude))
                .font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
            Spacer()
            Button {
                var updated = location
                updated = SavedMapLocation(id: location.id, name: name, emoji: String(emoji.prefix(2)), latitude: location.latitude, longitude: location.longitude)
                onSave(updated)
                dismiss()
            } label: {
                Text("Save").font(.system(size: 15, weight: .semibold, design: .rounded))
                    .foregroundStyle(palette.primaryButtonText).frame(maxWidth: .infinity)
                    .padding(.vertical, 14).background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain).disabled(name.isEmpty)
            .padding(.horizontal, 16).padding(.bottom, 20)
        }
    }
}

// MARK: - Helpers

private func formatDuration(_ seconds: Double) -> String {
    let s = Int(seconds)
    let h = s / 3600
    let m = (s % 3600) / 60
    if h > 0 { return "\(h)h \(m)m" }
    return "\(m) min"
}

private func formatDistance(_ meters: Double) -> String {
    let miles = meters / 1609.344
    if miles < 0.1 { return "< 0.1 mi" }
    return String(format: "%.1f mi", miles)
}

extension Comparable {
    func clamped(to range: ClosedRange<Self>) -> Self {
        min(max(self, range.lowerBound), range.upperBound)
    }
}

// MARK: - Map Trip Analytics Page

// MARK: - Isochrone panel

private struct IsochronePanel: View {
    @ObservedObject var vm: RouteMapViewModel
    let palette: QuailThemePalette

    // Ordered 10→60 min: green to red
    private let ringColors: [Color] = [.green, Color(red:0.6,green:0.85,blue:0), .yellow, .orange, Color(red:1,green:0.4,blue:0), .red]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "clock.fill").foregroundStyle(.purple)
                Text("Travel Time Map")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                Spacer()
                Button { withAnimation { vm.toggleIsochroneMode() } } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(.secondary)
                }.buttonStyle(.plain)
            }

            // Mode toggle — always visible
            HStack(spacing: 8) {
                ForEach([RouteMapViewModel.IsochroneTransport.drive, .walk], id: \.self) { mode in
                    let label = mode == .drive ? "Driving" : "Walking"
                    let icon = mode == .drive ? "car.fill" : "figure.walk"
                    Button {
                        vm.isochroneTransport = mode
                        if let c = vm.isochroneCenter { vm.setIsochroneCenter(c) }
                    } label: {
                        Label(label, systemImage: icon)
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                            .foregroundStyle(vm.isochroneTransport == mode ? .white : .primary)
                            .padding(.horizontal, 12).padding(.vertical, 7)
                            .background(vm.isochroneTransport == mode ? Color.purple : Color.secondary.opacity(0.1), in: Capsule())
                    }.buttonStyle(.plain)
                }
                if vm.isochroneTransport == .walk {
                    Text("~\(String(format: "%.1f", vm.walkingSpeedMPS * 2.237)) mph")
                        .font(.system(size: 11, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }

            if vm.isochroneCenter == nil {
                Text("Tap the map to set a starting point.")
                    .font(.system(size: 13, design: .rounded))
                    .foregroundStyle(.secondary)
            } else if vm.isLoadingIsochrones {
                HStack(spacing: 8) {
                    ProgressView().scaleEffect(0.8)
                    Text("Calculating road-based ranges…")
                        .font(.system(size: 13, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            } else {
                // Legend
                HStack(spacing: 4) {
                    ForEach(Array(zip([10,20,30,40,50,60], ringColors)), id: \.0) { min, color in
                        HStack(spacing: 3) {
                            Circle().fill(color).frame(width: 9, height: 9)
                            Text("\(min)m")
                                .font(.system(size: 10, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                }
                Button {
                    vm.isochroneCenter = nil
                    vm.isochronePolygons = []
                } label: {
                    Label("Clear pin", systemImage: "mappin.slash")
                        .font(.system(size: 12, design: .rounded))
                        .foregroundStyle(.secondary)
                }.buttonStyle(.plain)
            }
        }
        .padding(14)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .shadow(color: .black.opacity(0.15), radius: 12, y: -4)
    }
}

struct MapTripAnalyticsPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @State private var trips: [[String: Any]] = []
    @State private var stats: [String: Any] = [:]
    @State private var isLoading = true

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        AppChromeFrame(
            title: "Trip History",
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            showsStandaloneBar: true,
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { navigator.show(.notifications) }
        ) {
            AppPageScroll(contentPadding: 14) {
                if isLoading {
                    HStack { Spacer(); ProgressView(); Spacer() }.padding(.vertical, 40)
                } else {
                    statsSection
                    tripsSection
                }
            }
        }
        .task { await load() }
    }

    private var statsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Overview")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 4)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                statCard(label: "Total Trips", value: "\(statInt("total_trips"))", icon: "car.fill", color: .blue)
                statCard(label: "Total Miles", value: String(format: "%.0f mi", statDouble("total_miles")), icon: "road.lanes", color: .green)
                statCard(label: "This Month", value: String(format: "%.0f mi", statDouble("miles_this_month")), icon: "calendar", color: .orange)
                statCard(label: "This Week", value: String(format: "%.0f mi", statDouble("miles_this_week")), icon: "7.circle.fill", color: .purple)
            }

            if statInt("total_trips") > 0 {
                HStack(spacing: 6) {
                    Image(systemName: "arrow.triangle.swap")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                    Text("Avg trip: \(String(format: "%.1f mi", statDouble("avg_miles")))")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 4)
            }
        }
    }

    private var tripsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Recent Trips")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 4)

            if trips.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "car.fill")
                        .font(.system(size: 28))
                        .foregroundStyle(palette.accent.opacity(0.4))
                    Text("No trips recorded yet")
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                    Text("Trips are saved automatically when you use navigation in Quail Maps.")
                        .font(.system(size: 12, design: .rounded))
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 32)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(trips.enumerated()), id: \.offset) { idx, trip in
                        tripRow(trip)
                        if idx < trips.count - 1 { Divider().padding(.leading, 14) }
                    }
                }
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
            }
        }
    }

    private func tripRow(_ trip: [String: Any]) -> some View {
        let dist = (trip["distance_miles"] as? Double) ?? 0
        let origin = (trip["origin_name"] as? String) ?? ""
        let dest = (trip["destination_name"] as? String) ?? ""
        let dateStr = (trip["started_at"] as? String) ?? ""
        let type = (trip["transport_type"] as? String) ?? "automobile"
        let icon = type == "transit" ? "bus.fill" : "car.fill"

        return HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color.blue.opacity(0.12))
                    .frame(width: 36, height: 36)
                Image(systemName: icon)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.blue)
            }

            VStack(alignment: .leading, spacing: 2) {
                if !dest.isEmpty {
                    Text(dest)
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .lineLimit(1)
                    if !origin.isEmpty {
                        Text("from \(origin)")
                            .font(.system(size: 11, design: .rounded))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                } else {
                    Text("Trip")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                }
                Text(formattedDate(dateStr))
                    .font(.system(size: 11, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Text(String(format: "%.1f mi", dist))
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(.primary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    private func statCard(label: String, value: String, icon: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(color)
                Spacer()
            }
            Text(value)
                .font(.system(size: 20, weight: .bold, design: .rounded))
            Text(label)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func statInt(_ key: String) -> Int { (stats[key] as? Int) ?? 0 }
    private func statDouble(_ key: String) -> Double { (stats[key] as? Double) ?? 0 }

    private func formattedDate(_ iso: String) -> String {
        let f = ISO8601DateFormatter()
        guard let d = f.date(from: iso) else { return iso }
        let out = DateFormatter()
        out.dateStyle = .medium
        out.timeStyle = .short
        return out.string(from: d)
    }

    private func load() async {
        async let t = try? QuailCashAPI.shared.fetchMapTrips()
        async let s = try? QuailCashAPI.shared.fetchMapTripStats()
        trips = (await t) ?? []
        stats = (await s) ?? [:]
        isLoading = false
    }
}
