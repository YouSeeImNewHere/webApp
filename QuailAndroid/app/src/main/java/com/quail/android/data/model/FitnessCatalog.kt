package com.quail.android.data.model

import com.quail.android.data.model.ExerciseCategory.CARDIO
import com.quail.android.data.model.ExerciseCategory.CORE
import com.quail.android.data.model.ExerciseCategory.LEGS
import com.quail.android.data.model.ExerciseCategory.PULL
import com.quail.android.data.model.ExerciseCategory.PUSH
import com.quail.android.data.model.ExerciseCategory.SKILL
import com.quail.android.data.model.ExerciseDifficulty.ADVANCED
import com.quail.android.data.model.ExerciseDifficulty.BEGINNER
import com.quail.android.data.model.ExerciseDifficulty.ELITE
import com.quail.android.data.model.ExerciseDifficulty.INTERMEDIATE
import com.quail.android.data.model.MuscleGroup.ABS
import com.quail.android.data.model.MuscleGroup.BACK
import com.quail.android.data.model.MuscleGroup.BICEPS
import com.quail.android.data.model.MuscleGroup.CALVES
import com.quail.android.data.model.MuscleGroup.CHEST
import com.quail.android.data.model.MuscleGroup.FOREARMS
import com.quail.android.data.model.MuscleGroup.GLUTES
import com.quail.android.data.model.MuscleGroup.HAMSTRINGS
import com.quail.android.data.model.MuscleGroup.OBLIQUES
import com.quail.android.data.model.MuscleGroup.QUADS
import com.quail.android.data.model.MuscleGroup.SHOULDERS
import com.quail.android.data.model.MuscleGroup.TRICEPS

/** Mirrors FitnessStore.swift's seedExercises()/seedProgressionPaths() — the
 * built-in calisthenics catalog. Ported as a hardcoded constant rather than a
 * backend table since it's identical static reference content on every
 * install; only workout history/routines/goals that *reference* these ids
 * need syncing. `id` is a stable slug, not a random UUID, so it survives
 * across reinstalls and stays consistent between platforms. */
val DEFAULT_EXERCISES: List<Exercise> = listOf(
    // PUSH
    Exercise("wall_pushup", "Wall Push-up", PUSH, listOf(CHEST, TRICEPS, SHOULDERS), BEGINNER, listOf(
        "Stand facing a wall, arms-width away.",
        "Place hands on the wall at shoulder width and height.",
        "Bend your elbows, lowering your chest toward the wall.",
        "Push back to the start. Keep your body straight throughout.",
    ), defaultSets = 3, defaultReps = 15),
    Exercise("incline_pushup", "Incline Push-up", PUSH, listOf(CHEST, TRICEPS, SHOULDERS), BEGINNER, listOf(
        "Place hands on an elevated surface (bench, step) at shoulder width.",
        "Walk feet back until your body forms a straight line.",
        "Lower your chest to the surface by bending your elbows.",
        "Push back up. The lower the surface, the harder the exercise.",
    ), defaultSets = 3, defaultReps = 12),
    Exercise("pushup", "Push-up", PUSH, listOf(CHEST, TRICEPS, SHOULDERS, ABS), INTERMEDIATE, listOf(
        "Start in a high plank: hands slightly wider than shoulders, body straight.",
        "Brace your core and glutes — no sagging hips.",
        "Lower your chest to just above the floor, elbows at ~45° from your body.",
        "Push explosively back up to full arm extension.",
        "Breathe in on the way down, out on the way up.",
    ), defaultSets = 4, defaultReps = 15),
    Exercise("diamond_pushup", "Diamond Push-up", PUSH, listOf(TRICEPS, CHEST, SHOULDERS), INTERMEDIATE, listOf(
        "Form a diamond shape with your index fingers and thumbs touching.",
        "Place hands in the center of your chest in high plank position.",
        "Lower your chest toward your hands, keeping elbows close to your body.",
        "Push back up. This variation heavily targets the triceps.",
    ), defaultSets = 3, defaultReps = 10),
    Exercise("archer_pushup", "Archer Push-up", PUSH, listOf(CHEST, TRICEPS, SHOULDERS), ADVANCED, listOf(
        "Start in a wide push-up stance, much wider than normal.",
        "Shift your weight to one side as you lower — that arm bends, the other stays straight.",
        "The straight arm provides some assistance but the bent arm does the work.",
        "Alternate sides. This is the key step toward one-arm push-ups.",
    ), defaultSets = 3, defaultReps = 6),
    Exercise("pseudo_planche_pushup", "Pseudo Planche Push-up", PUSH, listOf(CHEST, TRICEPS, SHOULDERS, ABS), ADVANCED, listOf(
        "Begin in push-up position, but lean your body forward so shoulders are over or past your hands.",
        "Rotate hands outward so fingers point to the sides or slightly back.",
        "Maintain constant forward body lean as you lower and push.",
        "This trains the anterior deltoids and chest for planche progressions.",
    ), defaultSets = 3, defaultReps = 8),
    Exercise("one_arm_pushup", "One-Arm Push-up", PUSH, listOf(CHEST, TRICEPS, SHOULDERS, ABS, OBLIQUES), ELITE, listOf(
        "Start in push-up position, feet wider than normal for balance.",
        "Place one hand behind your back, shift weight to the working arm.",
        "Keep hips square to the ground — resist the urge to rotate.",
        "Lower slowly with control, push back up. Lock your core the entire time.",
    ), defaultSets = 3, defaultReps = 5),
    Exercise("pike_pushup", "Pike Push-up", PUSH, listOf(SHOULDERS, TRICEPS), INTERMEDIATE, listOf(
        "Start in downward dog: hips high, forming an inverted V.",
        "Hands shoulder-width apart, fingers spread for stability.",
        "Bend elbows and lower the top of your head toward the floor.",
        "Push back up. This trains vertical pressing for handstand push-ups.",
    ), defaultSets = 3, defaultReps = 8),
    Exercise("handstand_pushup", "Handstand Push-up", PUSH, listOf(SHOULDERS, TRICEPS), ELITE, listOf(
        "Kick up into a wall handstand, chest facing wall.",
        "With control, bend your elbows and lower your head toward the floor.",
        "Stop just before your head touches, then press back to full extension.",
        "Only attempt this after achieving a solid 60-second wall handstand hold.",
    ), defaultSets = 3, defaultReps = 5),

    // PULL
    Exercise("dead_hang", "Dead Hang", PULL, listOf(BACK, FOREARMS, SHOULDERS), BEGINNER, listOf(
        "Grip a pull-up bar with both hands, shoulder-width apart.",
        "Let your body hang fully — shoulders should rise to your ears.",
        "Relax your lower body and breathe steadily.",
        "Hold for time. This builds grip strength and decompresses the spine.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 30),
    Exercise("scapular_pullup", "Scapular Pull-up", PULL, listOf(BACK, SHOULDERS), BEGINNER, listOf(
        "Hang from a bar with straight arms.",
        "Without bending your elbows, depress and retract your shoulder blades.",
        "Your body should rise 2–3 inches through shoulder blade movement only.",
        "Lower slowly. This teaches proper scapular engagement before pulling.",
    ), defaultSets = 3, defaultReps = 10),
    Exercise("inverted_row", "Inverted Row", PULL, listOf(BACK, BICEPS, FOREARMS), BEGINNER, listOf(
        "Set a bar at hip height. Lie beneath it and grip it with straight arms.",
        "Keep your body in a straight line from head to heels.",
        "Pull your chest up to the bar by retracting your shoulder blades.",
        "Lower slowly. Elevate feet to increase difficulty.",
    ), defaultSets = 3, defaultReps = 10),
    Exercise("negative_pullup", "Negative Pull-up", PULL, listOf(BACK, BICEPS, FOREARMS), INTERMEDIATE, listOf(
        "Jump or step up so your chin is above the bar.",
        "Slowly lower yourself over 5–10 seconds, resisting gravity the entire time.",
        "Once at full extension, step down and repeat.",
        "Negatives build pulling strength faster than partial reps.",
    ), defaultSets = 4, defaultReps = 5),
    Exercise("pullup", "Pull-up", PULL, listOf(BACK, BICEPS, FOREARMS), INTERMEDIATE, listOf(
        "Grip bar with overhand grip, slightly wider than shoulders.",
        "Start from a dead hang with straight arms.",
        "Pull your elbows down and back, driving your chest to the bar.",
        "Hold briefly at the top, then lower under control.",
    ), defaultSets = 4, defaultReps = 8),
    Exercise("chinup", "Chin-up", PULL, listOf(BICEPS, BACK, FOREARMS), INTERMEDIATE, listOf(
        "Grip bar underhand (palms facing you), shoulder-width apart.",
        "Pull your chin above the bar, focusing on squeezing biceps.",
        "Lower slowly to full extension.",
        "Chin-ups have more bicep involvement than pull-ups.",
    ), defaultSets = 4, defaultReps = 8),
    Exercise("archer_pullup", "Archer Pull-up", PULL, listOf(BACK, BICEPS, FOREARMS), ADVANCED, listOf(
        "Take a wide grip on the bar — much wider than shoulder width.",
        "Pull toward one hand while keeping the other arm nearly straight.",
        "The straight arm assists but the bent arm does the primary work.",
        "Alternate sides. This bridges from two-arm to one-arm pulling.",
    ), defaultSets = 3, defaultReps = 5),
    Exercise("muscleup", "Muscle-up", PULL, listOf(BACK, BICEPS, CHEST, TRICEPS, FOREARMS), ELITE, listOf(
        "Start with an explosive pull-up — your hips should drive upward.",
        "As your chest reaches bar height, transition: lean forward and rotate wrists over the bar.",
        "Once above the bar, straighten your arms into a dip lockout position.",
        "Lower under control in reverse. Requires both pulling and pushing strength.",
    ), defaultSets = 3, defaultReps = 4),
    Exercise("one_arm_pullup", "One-Arm Pull-up", PULL, listOf(BACK, BICEPS, FOREARMS), ELITE, listOf(
        "Grip the bar with one hand, offset your other hand on your wrist for initial assistance.",
        "Pull your chin above the bar using primarily the gripping arm.",
        "Progress toward full one-arm by gradually reducing assistance hand involvement.",
        "A full one-arm pull-up requires months of targeted training.",
    ), defaultSets = 3, defaultReps = 3),

    // LEGS
    Exercise("bodyweight_squat", "Bodyweight Squat", LEGS, listOf(QUADS, GLUTES, HAMSTRINGS), BEGINNER, listOf(
        "Stand with feet shoulder-width apart, toes slightly out.",
        "Brace your core, keep chest up, and sit back as if into a chair.",
        "Lower until thighs are parallel to the floor — or deeper if mobility allows.",
        "Drive through heels to stand. Keep knees tracking over toes.",
    ), defaultSets = 3, defaultReps = 20),
    Exercise("bulgarian_split_squat", "Bulgarian Split Squat", LEGS, listOf(QUADS, GLUTES, HAMSTRINGS), INTERMEDIATE, listOf(
        "Stand in front of a bench or elevated surface. Place one foot on it behind you.",
        "Lower your back knee toward the ground, keeping your front shin vertical.",
        "Push through your front heel to return to standing.",
        "This heavily loads the front leg and challenges balance and hip flexibility.",
    ), defaultSets = 3, defaultReps = 10),
    Exercise("nordic_curl", "Nordic Curl", LEGS, listOf(HAMSTRINGS, GLUTES), ADVANCED, listOf(
        "Kneel on a mat and anchor your ankles under a stable object.",
        "With a straight body line from knee to head, slowly lower yourself forward.",
        "Use your hands to catch yourself at the bottom.",
        "Contract your hamstrings as hard as possible to pull yourself back up.",
        "One of the most effective exercises for hamstring strength and injury prevention.",
    ), defaultSets = 3, defaultReps = 5),
    Exercise("pistol_squat_negative", "Pistol Squat Negative", LEGS, listOf(QUADS, GLUTES, HAMSTRINGS, ABS), ADVANCED, listOf(
        "Balance on one leg, extend the other leg in front of you.",
        "Slowly lower over 5 seconds into a single-leg squat position.",
        "Use a hand on a wall or hold a support to stand back up.",
        "Focus on control and depth — sink as low as your mobility allows.",
    ), defaultSets = 3, defaultReps = 5),
    Exercise("pistol_squat", "Pistol Squat", LEGS, listOf(QUADS, GLUTES, HAMSTRINGS, ABS), ELITE, listOf(
        "Stand on one leg, extend the other forward and keep it straight.",
        "Squat all the way down until your glute touches your calf.",
        "Keep the extended leg off the ground throughout.",
        "Drive through your heel to stand. Requires full-body balance and leg strength.",
    ), defaultSets = 3, defaultReps = 6),
    Exercise("calf_raise", "Calf Raise", LEGS, listOf(CALVES), BEGINNER, listOf(
        "Stand on the edge of a step or flat ground, feet hip-width.",
        "Rise up onto the balls of your feet as high as possible.",
        "Pause at the top, then lower slowly below the step level for full stretch.",
        "Slow, full-range reps are more effective than fast, shallow ones.",
    ), defaultSets = 3, defaultReps = 20),

    // CORE
    Exercise("plank", "Plank", CORE, listOf(ABS, SHOULDERS, GLUTES), BEGINNER, listOf(
        "Place forearms on the floor, elbows under shoulders.",
        "Extend legs back so your body forms a straight line from head to heels.",
        "Squeeze your abs, glutes, and quads simultaneously.",
        "Breathe steadily. Don't let your hips sag or pike.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 45),
    Exercise("hollow_body_hold", "Hollow Body Hold", CORE, listOf(ABS, OBLIQUES), INTERMEDIATE, listOf(
        "Lie on your back and press your lower back into the floor.",
        "Raise your legs to 45° and arms overhead — both off the floor.",
        "The goal is a 'banana' body shape with your lower back glued down.",
        "If too hard, bend your knees or raise your legs higher. Build to straight legs and low.",
        "This is the foundation of gymnastics core strength.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 30),
    Exercise("hanging_knee_raise", "Hanging Knee Raise", CORE, listOf(ABS, OBLIQUES, FOREARMS), BEGINNER, listOf(
        "Hang from a pull-up bar with an overhand grip.",
        "Pull your knees up toward your chest by contracting your abs.",
        "Lower slowly — avoid swinging.",
        "Pause at the bottom before the next rep.",
    ), defaultSets = 3, defaultReps = 12),
    Exercise("hanging_leg_raise", "Hanging Leg Raise", CORE, listOf(ABS, OBLIQUES, FOREARMS), INTERMEDIATE, listOf(
        "Hang from a pull-up bar with a shoulder-width grip.",
        "Keeping legs straight, raise them to parallel or higher.",
        "Avoid swinging — the movement should be slow and controlled.",
        "Lower legs slowly, resisting gravity on the way down.",
    ), defaultSets = 3, defaultReps = 10),
    Exercise("toes_to_bar", "Toes to Bar", CORE, listOf(ABS, OBLIQUES, FOREARMS, BACK), ADVANCED, listOf(
        "Hang from a pull-up bar with a strong, stable grip.",
        "With straight legs, raise your toes to touch the bar.",
        "Control the descent — no kipping or swinging.",
        "Full range requires significant hamstring flexibility and core strength.",
    ), defaultSets = 3, defaultReps = 8),
    Exercise("ab_wheel_rollout", "Ab Wheel Rollout", CORE, listOf(ABS, OBLIQUES, SHOULDERS), ADVANCED, listOf(
        "Kneel on a mat, grip the ab wheel with both hands.",
        "Roll forward slowly, extending your body as far as you can while keeping your lower back neutral.",
        "Pause briefly, then contract your abs hard to pull the wheel back.",
        "Start with partial range, build to full extension over time.",
    ), defaultSets = 3, defaultReps = 8),

    // SKILL
    Exercise("crow_pose", "Crow Pose", SKILL, listOf(SHOULDERS, TRICEPS, ABS, FOREARMS), BEGINNER, listOf(
        "Squat down and place your hands on the ground, shoulder-width apart.",
        "Place your knees on the back of your upper arms, close to your armpits.",
        "Lean forward, shifting weight onto your hands until feet lift off.",
        "Hold the balance. Focus on looking forward, not down.",
        "This is the foundation of hand balancing.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 15),
    Exercise("wall_handstand", "Wall Handstand", SKILL, listOf(SHOULDERS, TRICEPS, ABS), INTERMEDIATE, listOf(
        "Face the wall, place hands 6 inches from the baseboard.",
        "Kick up into a handstand, letting your chest face the wall.",
        "Stack wrists under shoulders, shoulders over wrists.",
        "Point toes to the ceiling, engage your core and glutes.",
        "Practice shifting weight onto one hand to develop balance.",
    ), isTimedExercise = true, defaultSets = 4, defaultDurationSeconds = 30),
    Exercise("freestanding_handstand", "Freestanding Handstand", SKILL, listOf(SHOULDERS, TRICEPS, ABS, FOREARMS), ADVANCED, listOf(
        "Kick up from a lunge, leading with your dominant hand.",
        "Find balance by making micro-corrections with your fingertips.",
        "Keep your body in a straight vertical line — no banana shape.",
        "Exit forward into a forward roll or step down if you overbalance.",
        "Consistent 5-second holds typically require 300–500 hours of practice.",
    ), isTimedExercise = true, defaultSets = 5, defaultDurationSeconds = 10),
    Exercise("tuck_lsit", "Tuck L-sit", SKILL, listOf(ABS, TRICEPS, SHOULDERS, FOREARMS), INTERMEDIATE, listOf(
        "Sit on the floor, place hands beside your hips, fingers pointing forward.",
        "Press down through your hands to lift your hips off the floor.",
        "Bring your knees to your chest and hold the tuck position.",
        "Keep your arms straight — bent elbows make this much harder to hold.",
        "Build endurance before extending legs.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 20),
    Exercise("lsit", "L-sit", SKILL, listOf(ABS, TRICEPS, SHOULDERS, FOREARMS, QUADS), ADVANCED, listOf(
        "Support yourself on parallel bars, dip bars, or push-up handles.",
        "Lift your straight legs to hip height — forming an 'L' with your body.",
        "Keep your shoulders depressed and arms fully locked.",
        "Hold. Even 5 seconds is an excellent start.",
        "Progress from tuck by extending one leg, then both.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 15),
    Exercise("tuck_front_lever", "Tuck Front Lever", SKILL, listOf(BACK, ABS, SHOULDERS, FOREARMS), ADVANCED, listOf(
        "Hang from a pull-up bar, pull your knees to your chest.",
        "Retract your scapula and elevate your body until it's parallel to the floor.",
        "Your back should be flat and your hips tucked tight.",
        "Hold. The goal is a horizontal body position with no droop.",
        "This is the first step in the front lever skill progression.",
    ), isTimedExercise = true, defaultSets = 4, defaultDurationSeconds = 10),
    Exercise("front_lever", "Front Lever", SKILL, listOf(BACK, ABS, SHOULDERS, FOREARMS), ELITE, listOf(
        "Hang from a bar. With straight arms, pull your entire body to horizontal.",
        "Your body should be parallel to the floor, arms fully extended.",
        "Squeeze everything: lats, abs, quads, and glutes.",
        "This requires exceptional lat strength and body tension. Most athletes need 1–2 years of dedicated training.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 5),
    Exercise("tuck_back_lever", "Tuck Back Lever", SKILL, listOf(SHOULDERS, CHEST, ABS, FOREARMS), INTERMEDIATE, listOf(
        "Hold a bar overhead. Tuck your knees to your chest.",
        "Rotate backward (away from the bar) until your body is below and facing down.",
        "Your back should face the sky, body tucked and horizontal.",
        "This is generally easier than front lever. Important: warm up shoulders thoroughly first.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 15),
    Exercise("back_lever", "Back Lever", SKILL, listOf(SHOULDERS, CHEST, BACK, ABS), ADVANCED, listOf(
        "Perform the back lever with straight legs extended.",
        "Your body should be parallel to the floor, face down.",
        "Bicipital groove (inside the elbow) handles significant stress — only attempt after months of tuck practice.",
        "Requires full shoulder extension and excellent body tension.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 8),

    // CARDIO
    Exercise("running", "Running", CARDIO, listOf(QUADS, HAMSTRINGS, CALVES, GLUTES), BEGINNER, listOf(
        "Run at a comfortable pace where you can hold a conversation.",
        "Land mid-foot, not on your heel — shorter strides reduce impact.",
        "Keep your arms at 90° and swing them forward, not across your body.",
        "Breathe rhythmically: inhale for 2-3 steps, exhale for 2 steps.",
    ), isTimedExercise = true, defaultSets = 1, defaultDurationSeconds = 1800),
    Exercise("sprint_intervals", "Sprint Intervals", CARDIO, listOf(QUADS, HAMSTRINGS, CALVES, GLUTES), INTERMEDIATE, listOf(
        "Sprint at maximum effort for the set duration.",
        "Rest 1-2x the sprint duration between reps.",
        "Drive your knees up and push off your toes powerfully.",
        "Lean slightly forward from the ankles, not the waist.",
    ), isTimedExercise = true, defaultSets = 6, defaultDurationSeconds = 30),
    Exercise("jump_rope", "Jump Rope", CARDIO, listOf(CALVES, SHOULDERS, ABS), BEGINNER, listOf(
        "Hold the handles loosely — wrist rotation drives the rope, not your arms.",
        "Jump just high enough to clear the rope (1-2 inches).",
        "Land softly on the balls of your feet with slightly bent knees.",
        "Keep your elbows close to your sides throughout.",
    ), isTimedExercise = true, defaultSets = 3, defaultDurationSeconds = 60),
    Exercise("cycling", "Cycling", CARDIO, listOf(QUADS, HAMSTRINGS, GLUTES, CALVES), BEGINNER, listOf(
        "Set the seat height so your knee is slightly bent at the bottom of the pedal stroke.",
        "Push through the full pedal circle — pull up as well as push down.",
        "Keep your cadence around 80-90 RPM for aerobic work.",
        "Relax your upper body and grip; tension there wastes energy.",
    ), isTimedExercise = true, defaultSets = 1, defaultDurationSeconds = 1800),
    Exercise("burpees", "Burpees", CARDIO, listOf(CHEST, SHOULDERS, QUADS, ABS), INTERMEDIATE, listOf(
        "Stand, then drop your hands to the floor and jump feet back to a plank.",
        "Perform one push-up (optional but recommended).",
        "Jump feet back to your hands.",
        "Explode upward, fully extending hips, and clap overhead.",
    ), isTimedExercise = false, defaultSets = 3, defaultReps = 10),
    Exercise("box_jumps", "Box Jumps", CARDIO, listOf(QUADS, HAMSTRINGS, GLUTES, CALVES), INTERMEDIATE, listOf(
        "Stand arm's length from the box, feet hip-width apart.",
        "Swing your arms back, bend your knees, then explode upward.",
        "Land softly with both feet flat on the box, knees slightly bent.",
        "Stand tall, then step down one foot at a time — don't jump down.",
    ), isTimedExercise = false, defaultSets = 4, defaultReps = 8),
    Exercise("rowing_machine", "Rowing Machine", CARDIO, listOf(BACK, BICEPS, QUADS, GLUTES, ABS), BEGINNER, listOf(
        "The sequence is Legs → Body → Arms on the drive; reverse on recovery.",
        "Push with your legs first — they generate 60% of the power.",
        "At the finish, lean back slightly (11 o'clock) and pull elbows past your torso.",
        "Control the return: arms away first, then pivot the body, then slide forward.",
    ), isTimedExercise = true, defaultSets = 1, defaultDurationSeconds = 1200),
)

val DEFAULT_PROGRESSION_PATHS: List<ProgressionPath> = listOf(
    ProgressionPath("path_pushup", "Push-up", "From wall push-ups to one-arm push-ups.", PUSH,
        listOf("wall_pushup", "incline_pushup", "pushup", "archer_pushup", "one_arm_pushup")),
    ProgressionPath("path_handstand", "Handstand", "Vertical pressing from pike to freestanding HSPU.", PUSH,
        listOf("pike_pushup", "wall_handstand", "freestanding_handstand", "handstand_pushup")),
    ProgressionPath("path_pullup", "Pull-up", "Building a strong pull from hang to one-arm.", PULL,
        listOf("dead_hang", "scapular_pullup", "inverted_row", "negative_pullup", "pullup", "archer_pullup", "one_arm_pullup")),
    ProgressionPath("path_muscleup", "Muscle-up", "Combining pulling and pushing into one explosive movement.", PULL,
        listOf("pullup", "chinup", "muscleup")),
    ProgressionPath("path_pistol_squat", "Pistol Squat", "Single-leg squat from assisted to full.", LEGS,
        listOf("bodyweight_squat", "bulgarian_split_squat", "pistol_squat_negative", "pistol_squat")),
    ProgressionPath("path_core", "Core Control", "Building a bulletproof midsection.", CORE,
        listOf("plank", "hollow_body_hold", "hanging_knee_raise", "hanging_leg_raise", "toes_to_bar")),
    ProgressionPath("path_lsit", "L-sit", "Straight-arm compression strength.", SKILL,
        listOf("tuck_lsit", "lsit")),
    ProgressionPath("path_front_lever", "Front Lever", "Horizontal pulling strength from tuck to full.", SKILL,
        listOf("dead_hang", "tuck_front_lever", "front_lever")),
    ProgressionPath("path_back_lever", "Back Lever", "Shoulder extension and body tension.", SKILL,
        listOf("tuck_back_lever", "back_lever")),
)

fun exerciseById(id: String): Exercise? = DEFAULT_EXERCISES.firstOrNull { it.id == id }
