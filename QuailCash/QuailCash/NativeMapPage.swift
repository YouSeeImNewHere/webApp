import SwiftUI
import MapKit
import CoreLocation
import Combine

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
            onLeadingTap: { navigator.show(.mapSettings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: { _ in }
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
                // Route polyline
                if let route = vm.activeRoute {
                    MapPolyline(route.polyline)
                        .stroke(.blue, lineWidth: 4)
                }
            }
            .mapControls {
                MapUserLocationButton()
                MapCompass()
            }
            .ignoresSafeArea(edges: .all)
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            // Bottom panel
            RoutePanel(vm: vm, palette: palette)
                .background(.regularMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                .shadow(color: .black.opacity(0.12), radius: 12, y: -4)
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
        }
        .onAppear { vm.requestLocation() }
        .sheet(isPresented: $vm.showingSearchSheet) {
            LocationSearchSheet(vm: vm, palette: palette)
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $vm.showingDetourPicker) {
            DetourPickerSheet(vm: vm, palette: palette)
                .presentationDetents([.medium, .large])
        }
    }
}

// MARK: - Bottom route panel

private struct RoutePanel: View {
    @ObservedObject var vm: RouteMapViewModel
    let palette: QuailThemePalette

    var body: some View {
        VStack(spacing: 0) {
            // Drag handle
            Capsule()
                .fill(Color.secondary.opacity(0.4))
                .frame(width: 36, height: 4)
                .padding(.top, 10)
                .padding(.bottom, 6)

            VStack(spacing: 10) {
                // Origin row
                LocationRow(
                    icon: "location.fill",
                    iconColor: .blue,
                    placeholder: "Starting location",
                    value: vm.originName.isEmpty ? nil : vm.originName,
                    palette: palette
                ) {
                    vm.searchTarget = .origin
                    vm.showingSearchSheet = true
                }

                // Divider with swap
                HStack {
                    Rectangle().fill(palette.border).frame(height: 1)
                    Button { vm.swapLocations() } label: {
                        Image(systemName: "arrow.up.arrow.down")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(palette.chromeIconForeground)
                            .frame(width: 30, height: 30)
                            .background(palette.chromeIconBackground, in: Circle())
                            .overlay(Circle().stroke(palette.border, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    Rectangle().fill(palette.border).frame(height: 1)
                }

                // Destination row
                LocationRow(
                    icon: "mappin.circle.fill",
                    iconColor: .red,
                    placeholder: "Destination",
                    value: vm.destinationName.isEmpty ? nil : vm.destinationName,
                    palette: palette
                ) {
                    vm.searchTarget = .destination
                    vm.showingSearchSheet = true
                }
            }
            .padding(.horizontal, 14)

            // Route info + actions — show once destination is set
            if !vm.destinationName.isEmpty {
                Divider().padding(.vertical, 10)
                HStack(spacing: 10) {
                    if let route = vm.activeRoute {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(formatDuration(route.expectedTravelTime))
                                .font(.system(size: 17, weight: .bold, design: .rounded))
                            Text(formatDistance(route.distance))
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        Text("Set start to see route")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 8)
                    Button {
                        if vm.originCoordinate == nil { vm.useCurrentLocationAsOrigin() }
                        vm.showingDetourPicker = true
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: "plus.circle.fill")
                            Text("Add Stop")
                        }
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .lineLimit(1)
                        .foregroundStyle(palette.primaryButtonText)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 9)
                        .background(palette.primaryButton, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    Button {
                        vm.openInMaps()
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: "arrow.triangle.turn.up.right.circle.fill")
                            Text("Go")
                        }
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .lineLimit(1)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 9)
                        .background(Color.blue, in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 14)

                // Added detours
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
                                    Button {
                                        vm.removeDetour(detour)
                                    } label: {
                                        Image(systemName: "xmark")
                                            .font(.system(size: 10, weight: .bold))
                                            .foregroundStyle(.secondary)
                                    }
                                    .buttonStyle(.plain)
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(Color.secondary.opacity(0.12), in: Capsule())
                            }
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                    }
                }
            }

            Spacer(minLength: 0).frame(height: 12)
        }
        .frame(maxWidth: .infinity)
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
    @Published var addedDetours: [DetourWaypoint] = []

    @Published var showingSearchSheet = false
    @Published var showingDetourPicker = false
    @Published var searchTarget: SearchTarget = .destination
    @Published var locationResults: [MKMapItem] = []
    @Published var isSearching = false

    @Published var selectedDetourCategory: DetourCategory?
    @Published var detourResults: [DetourCandidate] = []
    @Published var isLoadingDetours = false

    private var locationDelegate: LocationDelegate?
    private let locationManager = CLLocationManager()
    private var searchTask: Task<Void, Never>?
    private var baseRouteTravelTime: Double = 0

    enum SearchTarget { case origin, destination }

    init() {
        let delegate = LocationDelegate { [weak self] coord in
            Task { @MainActor in
                self?.userLocation = coord
                if self?.originCoordinate == nil, self?.originName.isEmpty == true {
                    self?.cameraPosition = .region(MKCoordinateRegion(center: coord, latitudinalMeters: 5000, longitudinalMeters: 5000))
                }
            }
        }
        locationDelegate = delegate
        locationManager.delegate = delegate
        locationManager.desiredAccuracy = kCLLocationAccuracyHundredMeters
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

    func triggerRecalculate() { recalculateRoute() }

    private func recalculateRoute() {
        guard let origin = currentOriginCoordinate(), let destination = destinationCoordinate else { return }

        Task {
            var coords = [origin] + addedDetours.map(\.coordinate) + [destination]
            var segments: [MKRoute] = []
            for i in 0..<(coords.count - 1) {
                let req = MKDirections.Request()
                req.source = MKMapItem(placemark: MKPlacemark(coordinate: coords[i]))
                req.destination = MKMapItem(placemark: MKPlacemark(coordinate: coords[i + 1]))
                req.transportType = .automobile
                if let result = try? await MKDirections(request: req).calculate(),
                   let route = result.routes.first {
                    segments.append(route)
                }
            }
            // Merge polylines — use first segment as representative for display
            // and sum times
            if let first = segments.first {
                activeRoute = first
                baseRouteTravelTime = segments.reduce(0) { $0 + $1.expectedTravelTime }
            }
            // Zoom to fit route
            if let dest = destinationCoordinate {
                let center = CLLocationCoordinate2D(
                    latitude: (origin.latitude + dest.latitude) / 2,
                    longitude: (origin.longitude + dest.longitude) / 2
                )
                let span = MKCoordinateSpan(
                    latitudeDelta: abs(origin.latitude - dest.latitude) * 1.5 + 0.02,
                    longitudeDelta: abs(origin.longitude - dest.longitude) * 1.5 + 0.02
                )
                cameraPosition = .region(MKCoordinateRegion(center: center, span: span))
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
    let onLocation: (CLLocationCoordinate2D) -> Void
    init(onLocation: @escaping (CLLocationCoordinate2D) -> Void) {
        self.onLocation = onLocation
    }
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        onLocation(loc.coordinate)
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {}
}

// MARK: - Models

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
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: { _ in }
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
