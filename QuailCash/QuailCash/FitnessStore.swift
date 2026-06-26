import Foundation
import SwiftUI
import Combine
import HealthKit

// MARK: - Enums

enum ExerciseCategory: String, Codable, CaseIterable, Hashable {
    case push, pull, legs, core, skill, cardio

    var displayName: String {
        switch self {
        case .push:   return "Push"
        case .pull:   return "Pull"
        case .legs:   return "Legs"
        case .core:   return "Core"
        case .skill:  return "Skill"
        case .cardio: return "Cardio"
        }
    }

    var icon: String {
        switch self {
        case .push:   return "arrow.up.circle.fill"
        case .pull:   return "arrow.down.circle.fill"
        case .legs:   return "figure.walk"
        case .core:   return "circle.hexagongrid.fill"
        case .skill:  return "star.circle.fill"
        case .cardio: return "figure.run"
        }
    }

    var color: Color {
        switch self {
        case .push:   return Color(red: 0.95, green: 0.45, blue: 0.25)
        case .pull:   return Color(red: 0.25, green: 0.55, blue: 0.95)
        case .legs:   return Color(red: 0.35, green: 0.78, blue: 0.45)
        case .core:   return Color(red: 0.90, green: 0.65, blue: 0.10)
        case .skill:  return Color(red: 0.65, green: 0.35, blue: 0.95)
        case .cardio: return Color(red: 0.90, green: 0.25, blue: 0.55)
        }
    }
}

enum MuscleGroup: String, Codable, CaseIterable, Hashable {
    case chest, back, shoulders, triceps, biceps, forearms
    case quads, hamstrings, glutes, calves, abs, obliques

    var displayName: String {
        switch self {
        case .chest:      return "Chest"
        case .back:       return "Back"
        case .shoulders:  return "Shoulders"
        case .triceps:    return "Triceps"
        case .biceps:     return "Biceps"
        case .forearms:   return "Forearms"
        case .quads:      return "Quads"
        case .hamstrings: return "Hamstrings"
        case .glutes:     return "Glutes"
        case .calves:     return "Calves"
        case .abs:        return "Abs"
        case .obliques:   return "Obliques"
        }
    }
}

enum ExerciseDifficulty: String, Codable, CaseIterable, Hashable {
    case beginner, intermediate, advanced, elite

    var displayName: String {
        switch self {
        case .beginner:     return "Beginner"
        case .intermediate: return "Intermediate"
        case .advanced:     return "Advanced"
        case .elite:        return "Elite"
        }
    }

    var color: Color {
        switch self {
        case .beginner:     return Color(red: 0.25, green: 0.75, blue: 0.40)
        case .intermediate: return Color(red: 0.20, green: 0.55, blue: 0.95)
        case .advanced:     return Color(red: 0.90, green: 0.50, blue: 0.10)
        case .elite:        return Color(red: 0.85, green: 0.20, blue: 0.30)
        }
    }

    var sortKey: Int {
        switch self {
        case .beginner: return 0; case .intermediate: return 1
        case .advanced: return 2; case .elite: return 3
        }
    }
}

// MARK: - Exercise

struct Exercise: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var name: String
    var category: ExerciseCategory
    var muscleGroups: [MuscleGroup]
    var difficulty: ExerciseDifficulty
    var instructions: [String]
    var videoURL: String?
    var isTimedExercise: Bool = false
    var defaultSets: Int = 3
    var defaultReps: Int = 10
    var defaultDurationSeconds: Int = 30
    var progressionPathID: UUID?
    var progressionOrder: Int?
    var isBuiltIn: Bool = true

    static func == (lhs: Exercise, rhs: Exercise) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

// MARK: - Progression Path

struct ProgressionPath: Codable, Identifiable {
    var id: UUID = UUID()
    var name: String
    var description: String
    var category: ExerciseCategory
    var exerciseIDs: [UUID]
}

// MARK: - Workout Models

struct WorkoutSet: Codable, Identifiable {
    var id: UUID = UUID()
    var reps: Int?
    var durationSeconds: Int?
    var addedWeightKg: Double?
    var isCompleted: Bool = false
    var rpe: Int?
    var restSeconds: Int?

    var displayValue: String {
        if let d = durationSeconds { return "\(d)s" }
        if let r = reps { return "\(r) reps" }
        return "—"
    }
}

struct WorkoutRoutine: Codable, Identifiable {
    var id: UUID = UUID()
    var name: String
    var exercises: [WorkoutExercise]
    var createdAt: Date = Date()
}

// MARK: - Goals

enum FitnessGoalType: String, Codable, CaseIterable {
    case muscleMass, strength, endurance, fatLoss

    var displayName: String {
        switch self {
        case .muscleMass: return "Muscle Mass"
        case .strength:   return "Strength"
        case .endurance:  return "Endurance"
        case .fatLoss:    return "Fat Loss"
        }
    }
    var icon: String {
        switch self {
        case .muscleMass: return "figure.strengthtraining.functional"
        case .strength:   return "bolt.fill"
        case .endurance:  return "figure.run"
        case .fatLoss:    return "flame.fill"
        }
    }
    var color: Color {
        switch self {
        case .muscleMass: return Color(red: 0.25, green: 0.55, blue: 0.95)
        case .strength:   return Color(red: 0.90, green: 0.50, blue: 0.10)
        case .endurance:  return Color(red: 0.35, green: 0.78, blue: 0.45)
        case .fatLoss:    return Color(red: 0.90, green: 0.25, blue: 0.55)
        }
    }
    var repRange: String {
        switch self {
        case .muscleMass: return "8–15 reps"
        case .strength:   return "3–6 reps"
        case .endurance:  return "15–25 reps"
        case .fatLoss:    return "12–20 reps"
        }
    }
    var setsAdvice: String {
        switch self {
        case .muscleMass: return "3–5 sets per exercise"
        case .strength:   return "4–6 sets per exercise"
        case .endurance:  return "2–4 sets, higher volume"
        case .fatLoss:    return "3–4 sets, shorter rest"
        }
    }
    var restAdvice: String {
        switch self {
        case .muscleMass: return "60–90 seconds"
        case .strength:   return "2–5 minutes"
        case .endurance:  return "30–60 seconds"
        case .fatLoss:    return "30–45 seconds"
        }
    }
    var frequencyAdvice: String {
        switch self {
        case .muscleMass: return "Each muscle 2–3× per week"
        case .strength:   return "3–4 sessions per week, full rest days"
        case .endurance:  return "4–5 sessions per week"
        case .fatLoss:    return "4–5 sessions, mix strength & cardio"
        }
    }
    var strategyNotes: [String] {
        switch self {
        case .muscleMass:
            return [
                "Add reps before moving to a harder variation — this is calisthenics progressive overload.",
                "Track your weekly sets per muscle group. 12–20 sets/week is the hypertrophy sweet spot.",
                "Eat at a modest calorie surplus (~250–500 kcal/day) with 0.7–1g of protein per lb bodyweight.",
                "Prioritise compound movements: push-ups, pull-ups, dips, rows, squats.",
                "Sleep 7–9 hours — muscle is built during recovery, not during the workout."
            ]
        case .strength:
            return [
                "Skill progressions (L-sit, front lever, handstand) build relative strength fast because bodyweight never increases the way a barbell does.",
                "Practise the hardest variation you can do for 2–4 clean reps, rest fully, repeat.",
                "Frequency beats volume at high intensities — 3–4 sets of hard work beats 10 sets of sloppy reps.",
                "Greasing the groove: practice at 50–60% of max effort multiple times a day to build neural efficiency.",
                "Adequate protein and sleep are non-negotiable — central nervous system recovery takes 48–72h after maximal efforts."
            ]
        case .endurance:
            return [
                "Build aerobic base first: 20–40 min of easy cardio (Zone 2) 3–4× per week before adding HIIT.",
                "Increase total volume by no more than 10% per week to avoid overuse injury.",
                "Add sprint or HIIT sessions once your aerobic base is solid — 1–2 per week maximum.",
                "Run/cycle easy enough that you can hold a full conversation. Zone 2 is your fat-burning engine.",
                "Combine calisthenics circuits with cardio for full-body conditioning without equipment."
            ]
        case .fatLoss:
            return [
                "Fat loss is driven by a calorie deficit — exercise helps, but diet is the main lever.",
                "Preserve muscle by keeping protein high (0.7–1g/lb) and resistance training 3× per week.",
                "Minimise rest between sets (30–45s) to elevate heart rate and burn more calories.",
                "Circuit training (full body, no rest between exercises) maximises calorie burn per session.",
                "Cardio after weights burns more fat — glycogen is depleted so you go straight to fat as fuel."
            ]
        }
    }
}

struct FitnessGoal: Codable, Identifiable {
    var id: UUID = UUID()
    var title: String
    var goalType: FitnessGoalType
    var targetExerciseID: UUID?
    var targetReps: Int?
    var targetDurationSeconds: Int?
    var targetDate: Date
    var notes: String = ""
    var createdAt: Date = Date()
}

struct WorkoutExercise: Codable, Identifiable {
    var id: UUID = UUID()
    var exerciseID: UUID
    var sets: [WorkoutSet]
    var notes: String = ""
}

struct WorkoutSession: Codable, Identifiable {
    var id: UUID = UUID()
    var date: Date = Date()
    var exercises: [WorkoutExercise] = []
    var durationMinutes: Int = 0
    var bodyweightKg: Double?
    var notes: String = ""
    var hkWorkoutUUID: String?

    var totalSets: Int { exercises.reduce(0) { $0 + $1.sets.filter(\.isCompleted).count } }
    var totalReps: Int {
        exercises.flatMap(\.sets).filter(\.isCompleted).compactMap(\.reps).reduce(0, +)
    }
}

// MARK: - Milestone

struct FitnessMilestone: Codable, Identifiable {
    var id: UUID = UUID()
    var title: String
    var date: Date = Date()
    var exerciseID: UUID?
    var notes: String = ""
}

// MARK: - Health Snapshot

struct HealthSnapshot {
    var restingHR: Double?
    var hrv: Double?
    var sleepHours: Double?
    var todaySteps: Int = 0

    enum Readiness {
        case great, good, moderate, rest

        var label: String {
            switch self {
            case .great:    return "Ready to Train"
            case .good:     return "Good to Go"
            case .moderate: return "Take it Easy"
            case .rest:     return "Rest Day"
            }
        }

        var icon: String {
            switch self {
            case .great:    return "bolt.fill"
            case .good:     return "checkmark.circle.fill"
            case .moderate: return "minus.circle.fill"
            case .rest:     return "moon.fill"
            }
        }

        var color: Color {
            switch self {
            case .great:    return Color(red: 0.25, green: 0.78, blue: 0.45)
            case .good:     return Color(red: 0.20, green: 0.60, blue: 0.95)
            case .moderate: return Color(red: 0.90, green: 0.60, blue: 0.10)
            case .rest:     return Color(red: 0.80, green: 0.25, blue: 0.30)
            }
        }
    }

    var readiness: Readiness {
        var score = 0
        if let hrv = hrv {
            if hrv >= 50 { score += 2 } else if hrv >= 30 { score += 1 }
        }
        if let rhr = restingHR {
            if rhr <= 60 { score += 2 } else if rhr <= 70 { score += 1 }
        }
        if let sleep = sleepHours {
            if sleep >= 7 { score += 2 } else if sleep >= 5.5 { score += 1 }
        }
        if hrv == nil && restingHR == nil && sleepHours == nil { return .good }
        switch score {
        case 5...: return .great
        case 3...: return .good
        case 1...: return .moderate
        default:   return .rest
        }
    }
}

// MARK: - Store

@MainActor
final class FitnessStore: ObservableObject {
    static let shared = FitnessStore()

    @Published var exercises: [Exercise] = []
    @Published var progressionPaths: [ProgressionPath] = []
    @Published var sessions: [WorkoutSession] = []
    @Published var milestones: [FitnessMilestone] = []
    @Published var routines: [WorkoutRoutine] = []
    @Published var goals: [FitnessGoal] = []
    @Published var activeSession: WorkoutSession?
    @Published var healthSnapshot = HealthSnapshot()
    @Published var healthKitAvailable: Bool = HKHealthStore.isHealthDataAvailable()
    @Published var healthKitAuthorized: Bool = false

    private let hkStore = HKHealthStore()
    private var docs: URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0] }

    private init() {
        loadAll()
        if exercises.isEmpty { seedExercises() }
        if progressionPaths.isEmpty { seedProgressionPaths() }
        migrateExercisesIfNeeded()
        Task { await refreshHealthData() }
    }

    private func migrateExercisesIfNeeded() {
        let hasCardio = exercises.contains { $0.category == .cardio }
        if !hasCardio {
            let cardioSeeds: [Exercise] = [
                Exercise(name: "Running", category: .cardio, muscleGroups: [.quads, .hamstrings, .calves, .glutes], difficulty: .beginner, instructions: ["Run at a comfortable pace where you can hold a conversation.", "Land mid-foot — shorter strides reduce impact.", "Keep arms at 90° and swing forward, not across your body.", "Breathe rhythmically: inhale 2–3 steps, exhale 2 steps."], isTimedExercise: true, defaultSets: 1, defaultDurationSeconds: 1800),
                Exercise(name: "Sprint Intervals", category: .cardio, muscleGroups: [.quads, .hamstrings, .calves, .glutes], difficulty: .intermediate, instructions: ["Sprint at maximum effort for the set duration.", "Rest 1–2× the sprint duration between reps.", "Drive knees up and push off your toes powerfully.", "Lean slightly forward from the ankles, not the waist."], isTimedExercise: true, defaultSets: 6, defaultDurationSeconds: 30),
                Exercise(name: "Jump Rope", category: .cardio, muscleGroups: [.calves, .shoulders, .abs], difficulty: .beginner, instructions: ["Hold handles loosely — wrist rotation drives the rope.", "Jump just high enough to clear the rope (1–2 inches).", "Land softly on the balls of your feet, knees slightly bent.", "Keep elbows close to your sides."], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 60),
                Exercise(name: "Cycling", category: .cardio, muscleGroups: [.quads, .hamstrings, .glutes, .calves], difficulty: .beginner, instructions: ["Set seat height so knee is slightly bent at bottom of stroke.", "Push through the full pedal circle — pull up as well as push down.", "Aim for 80–90 RPM for aerobic work.", "Relax your upper body; tension there wastes energy."], isTimedExercise: true, defaultSets: 1, defaultDurationSeconds: 1800),
                Exercise(name: "Burpees", category: .cardio, muscleGroups: [.chest, .shoulders, .quads, .abs], difficulty: .intermediate, instructions: ["Drop hands to floor and jump feet back to a plank.", "Perform one push-up.", "Jump feet back to hands.", "Explode upward, extending hips fully, and clap overhead."], isTimedExercise: false, defaultSets: 3, defaultReps: 10),
                Exercise(name: "Box Jumps", category: .cardio, muscleGroups: [.quads, .hamstrings, .glutes, .calves], difficulty: .intermediate, instructions: ["Stand arm's length from the box, feet hip-width apart.", "Swing arms back, bend knees, then explode upward.", "Land softly with both feet flat on the box.", "Step down one foot at a time — don't jump down."], isTimedExercise: false, defaultSets: 4, defaultReps: 8),
                Exercise(name: "Rowing Machine", category: .cardio, muscleGroups: [.back, .biceps, .quads, .glutes, .abs], difficulty: .beginner, instructions: ["Sequence: Legs → Body → Arms on drive; reverse on recovery.", "Push with legs first — they generate 60% of power.", "At finish, lean back slightly and pull elbows past torso.", "Arms away first on return, then pivot body, then slide forward."], isTimedExercise: true, defaultSets: 1, defaultDurationSeconds: 1200),
            ]
            exercises.append(contentsOf: cardioSeeds)
            saveExercises()
        }
    }

    // MARK: - Persistence

    private func loadAll() {
        exercises       = load("fitness_exercises.json") ?? []
        progressionPaths = load("fitness_paths.json") ?? []
        sessions        = load("fitness_sessions.json") ?? []
        milestones      = load("fitness_milestones.json") ?? []
        routines        = load("fitness_routines.json") ?? []
        goals           = load("fitness_goals.json") ?? []
    }

    private func load<T: Decodable>(_ name: String) -> T? {
        let url = docs.appendingPathComponent(name)
        guard let data = try? Data(contentsOf: url) else { return nil }
        let dec = JSONDecoder(); dec.dateDecodingStrategy = .iso8601
        return try? dec.decode(T.self, from: data)
    }

    private func save<T: Encodable>(_ value: T, as name: String) {
        let url = docs.appendingPathComponent(name)
        let enc = JSONEncoder(); enc.dateEncodingStrategy = .iso8601; enc.outputFormatting = .prettyPrinted
        if let data = try? enc.encode(value) { try? data.write(to: url, options: .atomic) }
    }

    func saveExercises()  { save(exercises, as: "fitness_exercises.json") }
    func savePaths()      { save(progressionPaths, as: "fitness_paths.json") }
    func saveSessions()   { save(sessions, as: "fitness_sessions.json") }
    func saveMilestones() { save(milestones, as: "fitness_milestones.json") }
    func saveRoutines()   { save(routines, as: "fitness_routines.json") }
    func saveGoals()      { save(goals, as: "fitness_goals.json") }

    func addGoal(_ goal: FitnessGoal) { goals.insert(goal, at: 0); saveGoals() }
    func deleteGoal(id: UUID) { goals.removeAll { $0.id == id }; saveGoals() }

    func progressForGoal(_ goal: FitnessGoal) -> Double {
        guard let exID = goal.targetExerciseID, let pb = personalBest(for: exID) else { return 0 }
        if let target = goal.targetReps, let current = pb.reps {
            return min(1.0, Double(current) / Double(target))
        }
        if let target = goal.targetDurationSeconds, let current = pb.durationSeconds {
            return min(1.0, Double(current) / Double(target))
        }
        return 0
    }

    func saveAsRoutine(name: String, from session: WorkoutSession) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let exercises = session.exercises.map { we -> WorkoutExercise in
            var copy = we
            copy.sets = we.sets.map { s in
                WorkoutSet(reps: s.reps, durationSeconds: s.durationSeconds, addedWeightKg: s.addedWeightKg)
            }
            return copy
        }
        let routine = WorkoutRoutine(name: trimmed, exercises: exercises)
        routines.insert(routine, at: 0)
        saveRoutines()
    }

    func deleteRoutine(id: UUID) {
        routines.removeAll { $0.id == id }
        saveRoutines()
    }

    // MARK: - Active Workout

    func startWorkout(from routine: WorkoutRoutine? = nil, bodyweight: Double? = nil) {
        var session = WorkoutSession(bodyweightKg: bodyweight)
        if let routine {
            session.exercises = routine.exercises.map { we in
                var copy = we
                copy.id = UUID()
                copy.sets = we.sets.map { s in
                    var fresh = WorkoutSet(reps: s.reps, durationSeconds: s.durationSeconds, addedWeightKg: s.addedWeightKg)
                    fresh.restSeconds = s.restSeconds
                    return fresh
                }
                return copy
            }
        }
        activeSession = session
    }

    func addExercise(_ exercise: Exercise, to session: inout WorkoutSession) {
        let sets = (0..<exercise.defaultSets).map { _ -> WorkoutSet in
            exercise.isTimedExercise
                ? WorkoutSet(durationSeconds: exercise.defaultDurationSeconds)
                : WorkoutSet(reps: exercise.defaultReps)
        }
        session.exercises.append(WorkoutExercise(exerciseID: exercise.id, sets: sets))
    }

    func finishSession(_ session: WorkoutSession, durationMinutes: Int) {
        var finished = session
        finished.durationMinutes = durationMinutes
        sessions.insert(finished, at: 0)
        saveSessions()
        activeSession = nil
        Task { await writeWorkoutToHealthKit(finished) }
    }

    func cancelSession() { activeSession = nil }

    // MARK: - Queries

    func exercise(id: UUID) -> Exercise? { exercises.first { $0.id == id } }

    func recentSessions(count: Int = 10) -> [WorkoutSession] {
        Array(sessions.prefix(count))
    }

    func sessions(containing exerciseID: UUID, last days: Int = 90) -> [WorkoutSession] {
        let cutoff = Calendar.current.date(byAdding: .day, value: -days, to: Date()) ?? Date()
        return sessions.filter { s in
            s.date >= cutoff && s.exercises.contains { $0.exerciseID == exerciseID }
        }
    }

    func personalBest(for exerciseID: UUID) -> WorkoutSet? {
        let allSets = sessions.flatMap(\.exercises)
            .filter { $0.exerciseID == exerciseID }
            .flatMap(\.sets)
            .filter(\.isCompleted)
        let byReps = allSets.compactMap(\.reps).max()
        let byDur  = allSets.compactMap(\.durationSeconds).max()
        if let r = byReps { return WorkoutSet(reps: r, isCompleted: true) }
        if let d = byDur  { return WorkoutSet(durationSeconds: d, isCompleted: true) }
        return nil
    }

    func weeklyVolume() -> [MuscleGroup: Int] {
        let cutoff = Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? Date()
        var totals: [MuscleGroup: Int] = [:]
        for session in sessions where session.date >= cutoff {
            for we in session.exercises {
                guard let ex = exercise(id: we.exerciseID) else { continue }
                let reps = we.sets.filter(\.isCompleted).compactMap(\.reps).reduce(0, +)
                for muscle in ex.muscleGroups {
                    totals[muscle, default: 0] += reps
                }
            }
        }
        return totals
    }

    func currentProgressionStep(in path: ProgressionPath) -> (exercise: Exercise, stepIndex: Int)? {
        for (i, eid) in path.exerciseIDs.enumerated() {
            guard let ex = exercise(id: eid) else { continue }
            let pb = personalBest(for: eid)
            let threshold = ex.isTimedExercise ? 20 : ex.defaultReps
            let achieved = ex.isTimedExercise
                ? (pb?.durationSeconds ?? 0) >= threshold
                : (pb?.reps ?? 0) >= threshold
            if !achieved { return (ex, i) }
        }
        return exercises.first(where: { $0.id == path.exerciseIDs.last }).map { ($0, path.exerciseIDs.count - 1) }
    }

    func totalWorkoutsThisWeek() -> Int {
        let cutoff = Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? Date()
        return sessions.filter { $0.date >= cutoff }.count
    }

    // MARK: - Milestones

    func addMilestone(_ milestone: FitnessMilestone) {
        milestones.insert(milestone, at: 0)
        saveMilestones()
    }

    func deleteMilestone(id: UUID) {
        milestones.removeAll { $0.id == id }
        saveMilestones()
    }

    // MARK: - HealthKit

    func requestHealthKitAuthorization() async {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        let readTypes: Set<HKObjectType> = [
            HKQuantityType(.heartRate),
            HKQuantityType(.restingHeartRate),
            HKQuantityType(.heartRateVariabilitySDNN),
            HKQuantityType(.stepCount),
            HKQuantityType(.bodyMass),
            HKCategoryType(.sleepAnalysis),
        ]
        let writeTypes: Set<HKSampleType> = [
            HKWorkoutType.workoutType(),
            HKQuantityType(.activeEnergyBurned),
            HKQuantityType(.bodyMass),
        ]
        do {
            try await hkStore.requestAuthorization(toShare: writeTypes, read: readTypes)
            healthKitAuthorized = true
            await refreshHealthData()
        } catch {}
    }

    func refreshHealthData() async {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        async let rhr    = fetchLatestQuantity(.restingHeartRate, unit: .count().unitDivided(by: .minute()))
        async let hrv    = fetchLatestQuantity(.heartRateVariabilitySDNN, unit: .secondUnit(with: .milli))
        async let sleep  = fetchLastNightSleep()
        async let steps  = fetchTodaySteps()
        async let weight = fetchLatestQuantity(.bodyMass, unit: .gramUnit(with: .kilo))
        let (rhrVal, hrvVal, sleepVal, stepsVal, weightVal) = await (rhr, hrv, sleep, steps, weight)
        healthSnapshot = HealthSnapshot(
            restingHR: rhrVal,
            hrv: hrvVal,
            sleepHours: sleepVal,
            todaySteps: stepsVal
        )
        if let kg = weightVal {
            latestBodyMassKg = kg
        }
    }

    @Published var latestBodyMassKg: Double? = nil

    func saveBodyMass(_ kg: Double) async {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        let type = HKQuantityType(.bodyMass)
        let sample = HKQuantitySample(type: type, quantity: HKQuantity(unit: .gramUnit(with: .kilo), doubleValue: kg), start: Date(), end: Date())
        try? await hkStore.save(sample)
        latestBodyMassKg = kg
    }

    private func fetchLatestQuantity(_ identifier: HKQuantityTypeIdentifier, unit: HKUnit) async -> Double? {
        await withCheckedContinuation { continuation in
            let type = HKQuantityType(identifier)
            let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
            let query = HKSampleQuery(sampleType: type, predicate: nil, limit: 1, sortDescriptors: [sort]) { _, samples, _ in
                let val = (samples?.first as? HKQuantitySample)?.quantity.doubleValue(for: unit)
                continuation.resume(returning: val)
            }
            hkStore.execute(query)
        }
    }

    private func fetchLastNightSleep() async -> Double? {
        await withCheckedContinuation { continuation in
            let type = HKCategoryType(.sleepAnalysis)
            let start = Calendar.current.date(byAdding: .hour, value: -24, to: Date()) ?? Date()
            let pred = HKQuery.predicateForSamples(withStart: start, end: Date())
            let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
            let query = HKSampleQuery(sampleType: type, predicate: pred, limit: 20, sortDescriptors: [sort]) { _, samples, _ in
                let asleepValues: [HKCategoryValueSleepAnalysis] = [.asleepCore, .asleepDeep, .asleepREM]
                let hours = (samples as? [HKCategorySample])?
                    .filter { asleepValues.map(\.rawValue).contains($0.value) }
                    .reduce(0.0) { $0 + $1.endDate.timeIntervalSince($1.startDate) / 3600 }
                continuation.resume(returning: hours.flatMap { $0 > 0 ? $0 : nil })
            }
            hkStore.execute(query)
        }
    }

    private func fetchTodaySteps() async -> Int {
        await withCheckedContinuation { continuation in
            let type = HKQuantityType(.stepCount)
            let start = Calendar.current.startOfDay(for: Date())
            let pred = HKQuery.predicateForSamples(withStart: start, end: Date())
            let query = HKStatisticsQuery(quantityType: type, quantitySamplePredicate: pred, options: .cumulativeSum) { _, stats, _ in
                let steps = stats?.sumQuantity()?.doubleValue(for: .count()) ?? 0
                continuation.resume(returning: Int(steps))
            }
            hkStore.execute(query)
        }
    }

    func fetchHeartRateDuring(session: WorkoutSession) async -> [(Date, Double)] {
        await withCheckedContinuation { continuation in
            let type = HKQuantityType(.heartRate)
            let end = session.date.addingTimeInterval(Double(session.durationMinutes) * 60)
            let pred = HKQuery.predicateForSamples(withStart: session.date, end: end)
            let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)
            let query = HKSampleQuery(sampleType: type, predicate: pred, limit: 500, sortDescriptors: [sort]) { _, samples, _ in
                let bpms = (samples as? [HKQuantitySample])?.map { s in
                    (s.startDate, s.quantity.doubleValue(for: .count().unitDivided(by: .minute())))
                } ?? []
                continuation.resume(returning: bpms)
            }
            hkStore.execute(query)
        }
    }

    private func writeWorkoutToHealthKit(_ session: WorkoutSession) async {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        let end = session.date.addingTimeInterval(Double(max(session.durationMinutes, 1)) * 60)
        var metadata: [String: Any] = [HKMetadataKeyWorkoutBrandName: "Quail Fitness"]
        if let bw = session.bodyweightKg { metadata["BodyweightKg"] = bw }

        let workout = HKWorkout(
            activityType: .functionalStrengthTraining,
            start: session.date,
            end: end,
            duration: Double(session.durationMinutes) * 60,
            totalEnergyBurned: estimateCalories(session),
            totalDistance: nil,
            metadata: metadata
        )
        do {
            try await hkStore.save(workout)
            if let idx = sessions.firstIndex(where: { $0.id == session.id }) {
                sessions[idx].hkWorkoutUUID = workout.uuid.uuidString
                saveSessions()
            }
        } catch {}
    }

    private func estimateCalories(_ session: WorkoutSession) -> HKQuantity? {
        let bw = session.bodyweightKg ?? 75.0
        let met = 3.5
        let hours = Double(session.durationMinutes) / 60.0
        let kcal = met * bw * hours
        guard kcal > 0 else { return nil }
        return HKQuantity(unit: .kilocalorie(), doubleValue: kcal)
    }

    // MARK: - Default Data

    // swiftlint:disable function_body_length
    private func seedExercises() {
        var ex: [Exercise] = []

        // PUSH
        ex.append(Exercise(
            name: "Wall Push-up", category: .push,
            muscleGroups: [.chest, .triceps, .shoulders], difficulty: .beginner,
            instructions: [
                "Stand facing a wall, arms-width away.",
                "Place hands on the wall at shoulder width and height.",
                "Bend your elbows, lowering your chest toward the wall.",
                "Push back to the start. Keep your body straight throughout."
            ], isTimedExercise: false, defaultSets: 3, defaultReps: 15
        ))
        ex.append(Exercise(
            name: "Incline Push-up", category: .push,
            muscleGroups: [.chest, .triceps, .shoulders], difficulty: .beginner,
            instructions: [
                "Place hands on an elevated surface (bench, step) at shoulder width.",
                "Walk feet back until your body forms a straight line.",
                "Lower your chest to the surface by bending your elbows.",
                "Push back up. The lower the surface, the harder the exercise."
            ], defaultSets: 3, defaultReps: 12
        ))
        ex.append(Exercise(
            name: "Push-up", category: .push,
            muscleGroups: [.chest, .triceps, .shoulders, .abs], difficulty: .intermediate,
            instructions: [
                "Start in a high plank: hands slightly wider than shoulders, body straight.",
                "Brace your core and glutes — no sagging hips.",
                "Lower your chest to just above the floor, elbows at ~45° from your body.",
                "Push explosively back up to full arm extension.",
                "Breathe in on the way down, out on the way up."
            ], defaultSets: 4, defaultReps: 15
        ))
        ex.append(Exercise(
            name: "Diamond Push-up", category: .push,
            muscleGroups: [.triceps, .chest, .shoulders], difficulty: .intermediate,
            instructions: [
                "Form a diamond shape with your index fingers and thumbs touching.",
                "Place hands in the center of your chest in high plank position.",
                "Lower your chest toward your hands, keeping elbows close to your body.",
                "Push back up. This variation heavily targets the triceps."
            ], defaultSets: 3, defaultReps: 10
        ))
        ex.append(Exercise(
            name: "Archer Push-up", category: .push,
            muscleGroups: [.chest, .triceps, .shoulders], difficulty: .advanced,
            instructions: [
                "Start in a wide push-up stance, much wider than normal.",
                "Shift your weight to one side as you lower — that arm bends, the other stays straight.",
                "The straight arm provides some assistance but the bent arm does the work.",
                "Alternate sides. This is the key step toward one-arm push-ups."
            ], defaultSets: 3, defaultReps: 6
        ))
        ex.append(Exercise(
            name: "Pseudo Planche Push-up", category: .push,
            muscleGroups: [.chest, .triceps, .shoulders, .abs], difficulty: .advanced,
            instructions: [
                "Begin in push-up position, but lean your body forward so shoulders are over or past your hands.",
                "Rotate hands outward so fingers point to the sides or slightly back.",
                "Maintain constant forward body lean as you lower and push.",
                "This trains the anterior deltoids and chest for planche progressions."
            ], defaultSets: 3, defaultReps: 8
        ))
        ex.append(Exercise(
            name: "One-Arm Push-up", category: .push,
            muscleGroups: [.chest, .triceps, .shoulders, .abs, .obliques], difficulty: .elite,
            instructions: [
                "Start in push-up position, feet wider than normal for balance.",
                "Place one hand behind your back, shift weight to the working arm.",
                "Keep hips square to the ground — resist the urge to rotate.",
                "Lower slowly with control, push back up. Lock your core the entire time."
            ], defaultSets: 3, defaultReps: 5
        ))
        ex.append(Exercise(
            name: "Pike Push-up", category: .push,
            muscleGroups: [.shoulders, .triceps], difficulty: .intermediate,
            instructions: [
                "Start in downward dog: hips high, forming an inverted V.",
                "Hands shoulder-width apart, fingers spread for stability.",
                "Bend elbows and lower the top of your head toward the floor.",
                "Push back up. This trains vertical pressing for handstand push-ups."
            ], defaultSets: 3, defaultReps: 8
        ))
        ex.append(Exercise(
            name: "Handstand Push-up", category: .push,
            muscleGroups: [.shoulders, .triceps], difficulty: .elite,
            instructions: [
                "Kick up into a wall handstand, chest facing wall.",
                "With control, bend your elbows and lower your head toward the floor.",
                "Stop just before your head touches, then press back to full extension.",
                "Only attempt this after achieving a solid 60-second wall handstand hold."
            ], defaultSets: 3, defaultReps: 5
        ))

        // PULL
        ex.append(Exercise(
            name: "Dead Hang", category: .pull,
            muscleGroups: [.back, .forearms, .shoulders], difficulty: .beginner,
            instructions: [
                "Grip a pull-up bar with both hands, shoulder-width apart.",
                "Let your body hang fully — shoulders should rise to your ears.",
                "Relax your lower body and breathe steadily.",
                "Hold for time. This builds grip strength and decompresses the spine."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 30
        ))
        ex.append(Exercise(
            name: "Scapular Pull-up", category: .pull,
            muscleGroups: [.back, .shoulders], difficulty: .beginner,
            instructions: [
                "Hang from a bar with straight arms.",
                "Without bending your elbows, depress and retract your shoulder blades.",
                "Your body should rise 2–3 inches through shoulder blade movement only.",
                "Lower slowly. This teaches proper scapular engagement before pulling."
            ], defaultSets: 3, defaultReps: 10
        ))
        ex.append(Exercise(
            name: "Inverted Row", category: .pull,
            muscleGroups: [.back, .biceps, .forearms], difficulty: .beginner,
            instructions: [
                "Set a bar at hip height. Lie beneath it and grip it with straight arms.",
                "Keep your body in a straight line from head to heels.",
                "Pull your chest up to the bar by retracting your shoulder blades.",
                "Lower slowly. Elevate feet to increase difficulty."
            ], defaultSets: 3, defaultReps: 10
        ))
        ex.append(Exercise(
            name: "Negative Pull-up", category: .pull,
            muscleGroups: [.back, .biceps, .forearms], difficulty: .intermediate,
            instructions: [
                "Jump or step up so your chin is above the bar.",
                "Slowly lower yourself over 5–10 seconds, resisting gravity the entire time.",
                "Once at full extension, step down and repeat.",
                "Negatives build pulling strength faster than partial reps."
            ], defaultSets: 4, defaultReps: 5
        ))
        ex.append(Exercise(
            name: "Pull-up", category: .pull,
            muscleGroups: [.back, .biceps, .forearms], difficulty: .intermediate,
            instructions: [
                "Grip bar with overhand grip, slightly wider than shoulders.",
                "Start from a dead hang with straight arms.",
                "Pull your elbows down and back, driving your chest to the bar.",
                "Hold briefly at the top, then lower under control."
            ], defaultSets: 4, defaultReps: 8
        ))
        ex.append(Exercise(
            name: "Chin-up", category: .pull,
            muscleGroups: [.biceps, .back, .forearms], difficulty: .intermediate,
            instructions: [
                "Grip bar underhand (palms facing you), shoulder-width apart.",
                "Pull your chin above the bar, focusing on squeezing biceps.",
                "Lower slowly to full extension.",
                "Chin-ups have more bicep involvement than pull-ups."
            ], defaultSets: 4, defaultReps: 8
        ))
        ex.append(Exercise(
            name: "Archer Pull-up", category: .pull,
            muscleGroups: [.back, .biceps, .forearms], difficulty: .advanced,
            instructions: [
                "Take a wide grip on the bar — much wider than shoulder width.",
                "Pull toward one hand while keeping the other arm nearly straight.",
                "The straight arm assists but the bent arm does the primary work.",
                "Alternate sides. This bridges from two-arm to one-arm pulling."
            ], defaultSets: 3, defaultReps: 5
        ))
        ex.append(Exercise(
            name: "Muscle-up", category: .pull,
            muscleGroups: [.back, .biceps, .chest, .triceps, .forearms], difficulty: .elite,
            instructions: [
                "Start with an explosive pull-up — your hips should drive upward.",
                "As your chest reaches bar height, transition: lean forward and rotate wrists over the bar.",
                "Once above the bar, straighten your arms into a dip lockout position.",
                "Lower under control in reverse. Requires both pulling and pushing strength."
            ], defaultSets: 3, defaultReps: 4
        ))
        ex.append(Exercise(
            name: "One-Arm Pull-up", category: .pull,
            muscleGroups: [.back, .biceps, .forearms], difficulty: .elite,
            instructions: [
                "Grip the bar with one hand, offset your other hand on your wrist for initial assistance.",
                "Pull your chin above the bar using primarily the gripping arm.",
                "Progress toward full one-arm by gradually reducing assistance hand involvement.",
                "A full one-arm pull-up requires months of targeted training."
            ], defaultSets: 3, defaultReps: 3
        ))

        // LEGS
        ex.append(Exercise(
            name: "Bodyweight Squat", category: .legs,
            muscleGroups: [.quads, .glutes, .hamstrings], difficulty: .beginner,
            instructions: [
                "Stand with feet shoulder-width apart, toes slightly out.",
                "Brace your core, keep chest up, and sit back as if into a chair.",
                "Lower until thighs are parallel to the floor — or deeper if mobility allows.",
                "Drive through heels to stand. Keep knees tracking over toes."
            ], defaultSets: 3, defaultReps: 20
        ))
        ex.append(Exercise(
            name: "Bulgarian Split Squat", category: .legs,
            muscleGroups: [.quads, .glutes, .hamstrings], difficulty: .intermediate,
            instructions: [
                "Stand in front of a bench or elevated surface. Place one foot on it behind you.",
                "Lower your back knee toward the ground, keeping your front shin vertical.",
                "Push through your front heel to return to standing.",
                "This heavily loads the front leg and challenges balance and hip flexibility."
            ], defaultSets: 3, defaultReps: 10
        ))
        ex.append(Exercise(
            name: "Nordic Curl", category: .legs,
            muscleGroups: [.hamstrings, .glutes], difficulty: .advanced,
            instructions: [
                "Kneel on a mat and anchor your ankles under a stable object.",
                "With a straight body line from knee to head, slowly lower yourself forward.",
                "Use your hands to catch yourself at the bottom.",
                "Contract your hamstrings as hard as possible to pull yourself back up.",
                "One of the most effective exercises for hamstring strength and injury prevention."
            ], defaultSets: 3, defaultReps: 5
        ))
        ex.append(Exercise(
            name: "Pistol Squat Negative", category: .legs,
            muscleGroups: [.quads, .glutes, .hamstrings, .abs], difficulty: .advanced,
            instructions: [
                "Balance on one leg, extend the other leg in front of you.",
                "Slowly lower over 5 seconds into a single-leg squat position.",
                "Use a hand on a wall or hold a support to stand back up.",
                "Focus on control and depth — sink as low as your mobility allows."
            ], defaultSets: 3, defaultReps: 5
        ))
        ex.append(Exercise(
            name: "Pistol Squat", category: .legs,
            muscleGroups: [.quads, .glutes, .hamstrings, .abs], difficulty: .elite,
            instructions: [
                "Stand on one leg, extend the other forward and keep it straight.",
                "Squat all the way down until your glute touches your calf.",
                "Keep the extended leg off the ground throughout.",
                "Drive through your heel to stand. Requires full-body balance and leg strength."
            ], defaultSets: 3, defaultReps: 6
        ))
        ex.append(Exercise(
            name: "Calf Raise", category: .legs,
            muscleGroups: [.calves], difficulty: .beginner,
            instructions: [
                "Stand on the edge of a step or flat ground, feet hip-width.",
                "Rise up onto the balls of your feet as high as possible.",
                "Pause at the top, then lower slowly below the step level for full stretch.",
                "Slow, full-range reps are more effective than fast, shallow ones."
            ], defaultSets: 3, defaultReps: 20
        ))

        // CORE
        ex.append(Exercise(
            name: "Plank", category: .core,
            muscleGroups: [.abs, .shoulders, .glutes], difficulty: .beginner,
            instructions: [
                "Place forearms on the floor, elbows under shoulders.",
                "Extend legs back so your body forms a straight line from head to heels.",
                "Squeeze your abs, glutes, and quads simultaneously.",
                "Breathe steadily. Don't let your hips sag or pike."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 45
        ))
        ex.append(Exercise(
            name: "Hollow Body Hold", category: .core,
            muscleGroups: [.abs, .obliques], difficulty: .intermediate,
            instructions: [
                "Lie on your back and press your lower back into the floor.",
                "Raise your legs to 45° and arms overhead — both off the floor.",
                "The goal is a 'banana' body shape with your lower back glued down.",
                "If too hard, bend your knees or raise your legs higher. Build to straight legs and low.",
                "This is the foundation of gymnastics core strength."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 30
        ))
        ex.append(Exercise(
            name: "Hanging Knee Raise", category: .core,
            muscleGroups: [.abs, .obliques, .forearms], difficulty: .beginner,
            instructions: [
                "Hang from a pull-up bar with an overhand grip.",
                "Pull your knees up toward your chest by contracting your abs.",
                "Lower slowly — avoid swinging.",
                "Pause at the bottom before the next rep."
            ], defaultSets: 3, defaultReps: 12
        ))
        ex.append(Exercise(
            name: "Hanging Leg Raise", category: .core,
            muscleGroups: [.abs, .obliques, .forearms], difficulty: .intermediate,
            instructions: [
                "Hang from a pull-up bar with a shoulder-width grip.",
                "Keeping legs straight, raise them to parallel or higher.",
                "Avoid swinging — the movement should be slow and controlled.",
                "Lower legs slowly, resisting gravity on the way down."
            ], defaultSets: 3, defaultReps: 10
        ))
        ex.append(Exercise(
            name: "Toes to Bar", category: .core,
            muscleGroups: [.abs, .obliques, .forearms, .back], difficulty: .advanced,
            instructions: [
                "Hang from a pull-up bar with a strong, stable grip.",
                "With straight legs, raise your toes to touch the bar.",
                "Control the descent — no kipping or swinging.",
                "Full range requires significant hamstring flexibility and core strength."
            ], defaultSets: 3, defaultReps: 8
        ))
        ex.append(Exercise(
            name: "Ab Wheel Rollout", category: .core,
            muscleGroups: [.abs, .obliques, .shoulders], difficulty: .advanced,
            instructions: [
                "Kneel on a mat, grip the ab wheel with both hands.",
                "Roll forward slowly, extending your body as far as you can while keeping your lower back neutral.",
                "Pause briefly, then contract your abs hard to pull the wheel back.",
                "Start with partial range, build to full extension over time."
            ], defaultSets: 3, defaultReps: 8
        ))

        // SKILL
        ex.append(Exercise(
            name: "Crow Pose", category: .skill,
            muscleGroups: [.shoulders, .triceps, .abs, .forearms], difficulty: .beginner,
            instructions: [
                "Squat down and place your hands on the ground, shoulder-width apart.",
                "Place your knees on the back of your upper arms, close to your armpits.",
                "Lean forward, shifting weight onto your hands until feet lift off.",
                "Hold the balance. Focus on looking forward, not down.",
                "This is the foundation of hand balancing."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 15
        ))
        ex.append(Exercise(
            name: "Wall Handstand", category: .skill,
            muscleGroups: [.shoulders, .triceps, .abs], difficulty: .intermediate,
            instructions: [
                "Face the wall, place hands 6 inches from the baseboard.",
                "Kick up into a handstand, letting your chest face the wall.",
                "Stack wrists under shoulders, shoulders over wrists.",
                "Point toes to the ceiling, engage your core and glutes.",
                "Practice shifting weight onto one hand to develop balance."
            ], isTimedExercise: true, defaultSets: 4, defaultDurationSeconds: 30
        ))
        ex.append(Exercise(
            name: "Freestanding Handstand", category: .skill,
            muscleGroups: [.shoulders, .triceps, .abs, .forearms], difficulty: .advanced,
            instructions: [
                "Kick up from a lunge, leading with your dominant hand.",
                "Find balance by making micro-corrections with your fingertips.",
                "Keep your body in a straight vertical line — no banana shape.",
                "Exit forward into a forward roll or step down if you overbalance.",
                "Consistent 5-second holds typically require 300–500 hours of practice."
            ], isTimedExercise: true, defaultSets: 5, defaultDurationSeconds: 10
        ))
        ex.append(Exercise(
            name: "Tuck L-sit", category: .skill,
            muscleGroups: [.abs, .triceps, .shoulders, .forearms], difficulty: .intermediate,
            instructions: [
                "Sit on the floor, place hands beside your hips, fingers pointing forward.",
                "Press down through your hands to lift your hips off the floor.",
                "Bring your knees to your chest and hold the tuck position.",
                "Keep your arms straight — bent elbows make this much harder to hold.",
                "Build endurance before extending legs."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 20
        ))
        ex.append(Exercise(
            name: "L-sit", category: .skill,
            muscleGroups: [.abs, .triceps, .shoulders, .forearms, .quads], difficulty: .advanced,
            instructions: [
                "Support yourself on parallel bars, dip bars, or push-up handles.",
                "Lift your straight legs to hip height — forming an 'L' with your body.",
                "Keep your shoulders depressed and arms fully locked.",
                "Hold. Even 5 seconds is an excellent start.",
                "Progress from tuck by extending one leg, then both."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 15
        ))
        ex.append(Exercise(
            name: "Tuck Front Lever", category: .skill,
            muscleGroups: [.back, .abs, .shoulders, .forearms], difficulty: .advanced,
            instructions: [
                "Hang from a pull-up bar, pull your knees to your chest.",
                "Retract your scapula and elevate your body until it's parallel to the floor.",
                "Your back should be flat and your hips tucked tight.",
                "Hold. The goal is a horizontal body position with no droop.",
                "This is the first step in the front lever skill progression."
            ], isTimedExercise: true, defaultSets: 4, defaultDurationSeconds: 10
        ))
        ex.append(Exercise(
            name: "Front Lever", category: .skill,
            muscleGroups: [.back, .abs, .shoulders, .forearms], difficulty: .elite,
            instructions: [
                "Hang from a bar. With straight arms, pull your entire body to horizontal.",
                "Your body should be parallel to the floor, arms fully extended.",
                "Squeeze everything: lats, abs, quads, and glutes.",
                "This requires exceptional lat strength and body tension. Most athletes need 1–2 years of dedicated training."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 5
        ))
        ex.append(Exercise(
            name: "Tuck Back Lever", category: .skill,
            muscleGroups: [.shoulders, .chest, .abs, .forearms], difficulty: .intermediate,
            instructions: [
                "Hold a bar overhead. Tuck your knees to your chest.",
                "Rotate backward (away from the bar) until your body is below and facing down.",
                "Your back should face the sky, body tucked and horizontal.",
                "This is generally easier than front lever. Important: warm up shoulders thoroughly first."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 15
        ))
        ex.append(Exercise(
            name: "Back Lever", category: .skill,
            muscleGroups: [.shoulders, .chest, .back, .abs], difficulty: .advanced,
            instructions: [
                "Perform the back lever with straight legs extended.",
                "Your body should be parallel to the floor, face down.",
                "Bicipital groove (inside the elbow) handles significant stress — only attempt after months of tuck practice.",
                "Requires full shoulder extension and excellent body tension."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 8
        ))

        // CARDIO
        ex.append(Exercise(
            name: "Running", category: .cardio,
            muscleGroups: [.quads, .hamstrings, .calves, .glutes], difficulty: .beginner,
            instructions: [
                "Run at a comfortable pace where you can hold a conversation.",
                "Land mid-foot, not on your heel — shorter strides reduce impact.",
                "Keep your arms at 90° and swing them forward, not across your body.",
                "Breathe rhythmically: inhale for 2-3 steps, exhale for 2 steps."
            ], isTimedExercise: true, defaultSets: 1, defaultDurationSeconds: 1800
        ))
        ex.append(Exercise(
            name: "Sprint Intervals", category: .cardio,
            muscleGroups: [.quads, .hamstrings, .calves, .glutes], difficulty: .intermediate,
            instructions: [
                "Sprint at maximum effort for the set duration.",
                "Rest 1-2x the sprint duration between reps.",
                "Drive your knees up and push off your toes powerfully.",
                "Lean slightly forward from the ankles, not the waist."
            ], isTimedExercise: true, defaultSets: 6, defaultDurationSeconds: 30
        ))
        ex.append(Exercise(
            name: "Jump Rope", category: .cardio,
            muscleGroups: [.calves, .shoulders, .abs], difficulty: .beginner,
            instructions: [
                "Hold the handles loosely — wrist rotation drives the rope, not your arms.",
                "Jump just high enough to clear the rope (1-2 inches).",
                "Land softly on the balls of your feet with slightly bent knees.",
                "Keep your elbows close to your sides throughout."
            ], isTimedExercise: true, defaultSets: 3, defaultDurationSeconds: 60
        ))
        ex.append(Exercise(
            name: "Cycling", category: .cardio,
            muscleGroups: [.quads, .hamstrings, .glutes, .calves], difficulty: .beginner,
            instructions: [
                "Set the seat height so your knee is slightly bent at the bottom of the pedal stroke.",
                "Push through the full pedal circle — pull up as well as push down.",
                "Keep your cadence around 80-90 RPM for aerobic work.",
                "Relax your upper body and grip; tension there wastes energy."
            ], isTimedExercise: true, defaultSets: 1, defaultDurationSeconds: 1800
        ))
        ex.append(Exercise(
            name: "Burpees", category: .cardio,
            muscleGroups: [.chest, .shoulders, .quads, .abs], difficulty: .intermediate,
            instructions: [
                "Stand, then drop your hands to the floor and jump feet back to a plank.",
                "Perform one push-up (optional but recommended).",
                "Jump feet back to your hands.",
                "Explode upward, fully extending hips, and clap overhead."
            ], isTimedExercise: false, defaultSets: 3, defaultReps: 10
        ))
        ex.append(Exercise(
            name: "Box Jumps", category: .cardio,
            muscleGroups: [.quads, .hamstrings, .glutes, .calves], difficulty: .intermediate,
            instructions: [
                "Stand arm's length from the box, feet hip-width apart.",
                "Swing your arms back, bend your knees, then explode upward.",
                "Land softly with both feet flat on the box, knees slightly bent.",
                "Stand tall, then step down one foot at a time — don't jump down."
            ], isTimedExercise: false, defaultSets: 4, defaultReps: 8
        ))
        ex.append(Exercise(
            name: "Rowing Machine", category: .cardio,
            muscleGroups: [.back, .biceps, .quads, .glutes, .abs], difficulty: .beginner,
            instructions: [
                "The sequence is Legs → Body → Arms on the drive; reverse on recovery.",
                "Push with your legs first — they generate 60% of the power.",
                "At the finish, lean back slightly (11 o'clock) and pull elbows past your torso.",
                "Control the return: arms away first, then pivot the body, then slide forward."
            ], isTimedExercise: true, defaultSets: 1, defaultDurationSeconds: 1200
        ))

        // Assign progression path IDs (will be updated after paths are created)
        self.exercises = ex
        saveExercises()
    }

    private func seedProgressionPaths() {
        guard !exercises.isEmpty else { return }

        func ids(_ names: [String]) -> [UUID] {
            names.compactMap { n in exercises.first { $0.name == n }?.id }
        }

        var paths: [ProgressionPath] = [
            ProgressionPath(name: "Push-up",      description: "From wall push-ups to one-arm push-ups.", category: .push,
                exerciseIDs: ids(["Wall Push-up","Incline Push-up","Push-up","Archer Push-up","One-Arm Push-up"])),
            ProgressionPath(name: "Handstand",    description: "Vertical pressing from pike to freestanding HSPU.", category: .push,
                exerciseIDs: ids(["Pike Push-up","Wall Handstand","Freestanding Handstand","Handstand Push-up"])),
            ProgressionPath(name: "Pull-up",      description: "Building a strong pull from hang to one-arm.", category: .pull,
                exerciseIDs: ids(["Dead Hang","Scapular Pull-up","Inverted Row","Negative Pull-up","Pull-up","Archer Pull-up","One-Arm Pull-up"])),
            ProgressionPath(name: "Muscle-up",    description: "Combining pulling and pushing into one explosive movement.", category: .pull,
                exerciseIDs: ids(["Pull-up","Chin-up","Muscle-up"])),
            ProgressionPath(name: "Pistol Squat", description: "Single-leg squat from assisted to full.", category: .legs,
                exerciseIDs: ids(["Bodyweight Squat","Bulgarian Split Squat","Pistol Squat Negative","Pistol Squat"])),
            ProgressionPath(name: "Core Control", description: "Building a bulletproof midsection.", category: .core,
                exerciseIDs: ids(["Plank","Hollow Body Hold","Hanging Knee Raise","Hanging Leg Raise","Toes to Bar"])),
            ProgressionPath(name: "L-sit",        description: "Straight-arm compression strength.", category: .skill,
                exerciseIDs: ids(["Tuck L-sit","L-sit"])),
            ProgressionPath(name: "Front Lever",  description: "Horizontal pulling strength from tuck to full.", category: .skill,
                exerciseIDs: ids(["Dead Hang","Tuck Front Lever","Front Lever"])),
            ProgressionPath(name: "Back Lever",   description: "Shoulder extension and body tension.", category: .skill,
                exerciseIDs: ids(["Tuck Back Lever","Back Lever"])),
        ]

        // Stamp path ID onto each exercise
        for path in paths {
            for (order, eid) in path.exerciseIDs.enumerated() {
                if let idx = exercises.firstIndex(where: { $0.id == eid }) {
                    exercises[idx].progressionPathID = path.id
                    exercises[idx].progressionOrder = order
                }
            }
        }

        self.progressionPaths = paths
        saveExercises()
        savePaths()
    }
    // swiftlint:enable function_body_length
}
