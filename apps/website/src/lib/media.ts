const evidence =
  "https://github.com/MarkUnthank/flyhard/tree/main/reports/2026-09-09-clean-videos";

// Newest entries first. Keep IDs stable so shared links keep pointing to an entry.
type MediaEntry = {
  id: string;
  number: string;
  date: string;
  dateLabel: string;
  category: string;
  title: string;
  intro: string;
  duration: string;
  playback: string;
  audio: string;
  paragraphs: string[];
  facts: string[];
  evidenceUrl: string;
  evidenceLabel: string;
  evidenceLink?: string;
  downloads?: { file: string; label: string }[];
  stills?: { file: string; caption: string }[];
};

export const mediaEntries: MediaEntry[] = [
  {
    id: "three-point-turn",
    number: "08",
    date: "2026-09-11",
    dateLabel: "11 September 2026",
    category: "Three-point turn",
    title: "A little change of direction.",
    intro:
      "Forward. Reverse. Forward. One complete attempt, with time to finish.",
    duration: "22.8 seconds",
    playback: "Normal simulation speed · 60 fps",
    audio: "Boccherini",
    paragraphs: [
      "The full successful validation take plays once, without skipping ahead: 20.3 seconds of driving, followed by a short hold on the finish. The fly chooses steering, speed and gear from structured road and goal geometry. Fixed motor helpers move its legs; the measured wheel, pedals and selector operate CARLA.",
      "This take finishes 25.4 cm from its target and 0.755° from the intended heading, with no collision. In eight separate held-out tests, six met the full stopping target. All eight completed the forward–reverse–forward sequence without contact or crossing the marked road boundary; two stopped just outside the position tolerance.",
      "These are small, scoped tests. There is no camera-based road understanding, and the model is an engineering interpretation of measured fly connectivity. Boccherini’s Minuet and Trio accompanies the complete attempt.",
    ],
    facts: [
      "6/8 held-out tests passed",
      "0/8 contacts or boundary crossings",
      "Complete 20.3-second validation take",
    ],
    evidenceUrl: "/press/data/three-point-turn-notes.md",
    evidenceLink: "Read the recording notes",
    evidenceLabel: "Test criteria, results, control chain & source reports",
    downloads: [
      {
        file: "/press/data/three-point-turn-results.json",
        label: "8-trial results · JSON",
      },
    ],
    stills: [
      {
        file: "three-point-turn.jpg",
        caption:
          "The Mini turns across the road in the complete validation take.",
      },
      {
        file: "three-point-turn-detail.jpg",
        caption: "Moving forward again as the same attempt continues.",
      },
      {
        file: "three-point-turn-finish.jpg",
        caption:
          "Approaching the final position, with recorded controls alongside.",
      },
    ],
  },
  {
    id: "road-rage",
    number: "07",
    date: "2026-09-10",
    dateLabel: "10 September 2026",
    category: "Horn experiment",
    title: "Small fly. Big feelings.",
    intro: "Three cars, a very long honk, and an actual pile-up.",
    duration: "20 seconds",
    playback: "Edited at normal simulation speed · 60 fps",
    audio: "Recorded car horn",
    paragraphs: [
      "The fly passes one car, collides with the next, and keeps holding the horn as a third joins the pile-up. Interior cuts show the recorded foreleg movement operating the button. The real horn recording is timed to measured button presses.",
      "This is a failed take, kept because the failure is part of the experiment. The source travelled 60.04 metres and produced two horn onsets, missing the test’s required 90 metres and three onsets. Its longest physical press lasted 16 seconds. The impacts and continuing hold remain in the edit; four seconds of waiting are removed.",
      "Traffic, route, speed and erratic steering requests are directed. The model supplies the measured wheel and horn actuation. The cabin fly is composited from the same recorded body motion; this is not a demonstration of autonomous driving.",
    ],
    facts: [
      "16-second longest horn press",
      "Actual collision retained",
      "Failed scenario, openly reported",
    ],
    evidenceUrl: "/press/data/horn-notes.md",
    evidenceLink: "Read the recording notes",
    evidenceLabel: "Dynamic scenarios, quiet-case failure & editing details",
    downloads: [
      {
        file: "/press/data/horn-diagnostic.json",
        label: "Held-out diagnostic · JSON",
      },
    ],
    stills: [
      {
        file: "road-rage.jpg",
        caption: "The Mini meets traffic in the directed road-rage scenario.",
      },
      {
        file: "road-rage-detail.jpg",
        caption: "A recorded encounter from the road-rage experiment.",
      },
    ],
  },
  {
    id: "horn-etiquette",
    number: "06",
    date: "2026-09-10",
    dateLabel: "10 September 2026",
    category: "Horn experiment",
    title: "Green means go. Apparently.",
    intro:
      "Moving traffic, two inconvenient pull-outs, and a foreleg on the horn.",
    duration: "37.5 seconds",
    playback: "Edited at normal simulation speed · 60 fps",
    audio: "Recorded car horn",
    paragraphs: [
      "Cars arrive at the lights, wait, and pull away. The fly honks 0.117 seconds after the light turns green behind a waiting car. It drives through an already-green light quietly, then meets cars pulling out at a T-junction and a crossroads. Interior shots show it holding the horn.",
      "The empty-road scene includes a brief, 83-millisecond false chirp. We kept it. None of these five source takes recorded an ego-vehicle collision, but a separate ten-case structured diagnostic passed only three of four positive horn cases and all six quiet cases. That small diagnostic does not guarantee quiet driving in CARLA.",
      "The learned controller operates the fly’s forelegs and physical horn button using structured inputs. Approaches, traffic, route and speed remain directed. The cabin body is a synchronized composite, and the recorded horn sound follows measured button contact.",
    ],
    facts: [
      "Five moving traffic scenes",
      "Two different pull-out scenarios",
      "False empty-road chirp retained",
    ],
    evidenceUrl: "/press/data/horn-notes.md",
    evidenceLink: "Read the recording notes",
    evidenceLabel: "Native recordings & the separate structured diagnostic",
    downloads: [
      {
        file: "/press/data/horn-diagnostic.json",
        label: "Held-out diagnostic · JSON",
      },
    ],
    stills: [
      {
        file: "horn-etiquette-detail.jpg",
        caption:
          "One of the moving traffic-light scenes in the horn experiment.",
      },
      {
        file: "horn-etiquette-cabin.jpg",
        caption: "Inside the cabin during a measured horn-button press.",
      },
    ],
  },
  {
    id: "parallel-parking",
    number: "05",
    date: "2026-09-10",
    dateLabel: "10 September 2026",
    category: "Parking experiment",
    title: "Fifty ways to miss a parking space.",
    intro:
      "Mozart, fifty attempts, and a parking test that remains very much unpassed.",
    duration: "30 seconds",
    playback: "Accelerated montage · 60 fps",
    audio: "Mozart",
    paragraphs: [
      "The edit builds to 32 views by 6.4 seconds, then jumps between individual attempts and the grid. All 50 trials appear as excerpts. The grid footage runs at 6× speed; the fly alongside is a separately looped replay, labelled in the film, and is not synchronized to each car.",
      "The result is 0/50 successful parks, with collision flags in ten trials. Resetting the learned core also produces 0/50, with twelve flagged trials. Flags include virtual-curb and vehicle-bound overlap as well as native collisions; they are not a count of individual crashes.",
      "The policy chooses steering, speed and gear from structured relative geometry, with fixed motor helpers moving the body. The measured controls drive CARLA. Lower final-position error than the reset comparison is useful evidence, but it does not establish successful parking. The original sponsor snapshot is preserved.",
    ],
    facts: [
      "0/50 successful parks",
      "10/50 collision-flagged trials",
      "Independent fly replay disclosed",
    ],
    evidenceUrl: "/press/data/parking-notes.md",
    evidenceLink: "Read the recording notes",
    evidenceLabel: "Parking gate, reset comparison & montage treatment",
    downloads: [
      {
        file: "/press/data/parking-trials.csv",
        label: "Per-trial results · CSV",
      },
      {
        file: "/press/data/parking-results.json",
        label: "Learned-core results · JSON",
      },
    ],
    stills: [
      {
        file: "parallel-parking.jpg",
        caption:
          "The parking montage builds through simultaneous recorded attempts.",
      },
      {
        file: "parallel-parking-detail.jpg",
        caption:
          "A single recorded parking attempt, with the independent fly replay labelled.",
      },
    ],
  },
  {
    id: "indicator-closeup",
    number: "04",
    date: "2026-09-10",
    dateLabel: "10 September 2026",
    category: "Indicator experiment",
    title: "A small indication of progress.",
    intro:
      "A closer look at the stalk, the flashing lamp, and the cancellation.",
    duration: "25 seconds",
    playback: "Slow motion · 60 fps",
    audio: "Silent",
    paragraphs: [
      "A new close-up edit of the recorded roundabout sequence follows the fly pulling the indicator stalk, the Mini’s native bumper lamp flashing, and the stalk returning as the signal switches off.",
      "The saved body motion and vehicle poses are replayed for this 60 fps slow-motion presentation. Navigation and speed remain engineered inputs. This is an inspection of the recorded control sequence, not a newly learned road-navigation result.",
    ],
    facts: [
      "1,500 rendered frames",
      "Stalk & native lamp views",
      "Recorded roundabout sequence",
    ],
    evidenceUrl: "/press/data/indicator-notes.md",
    evidenceLink: "Read the recording notes",
    evidenceLabel: "Source recording, timing & web export",
    stills: [
      {
        file: "indicator-closeup.jpg",
        caption: "The Mini’s bumper indicator in the close-up film.",
      },
      {
        file: "indicator-closeup-detail.jpg",
        caption: "A close view from the recorded indicator sequence.",
      },
    ],
  },
  {
    id: "roundabout",
    number: "03",
    date: "2026-09-10",
    dateLabel: "10 September 2026",
    category: "Roundabout experiment",
    title: "A turn for the ambitious.",
    intro: "A roundabout, an indicator, and seven sponsors along for the ride.",
    duration: "25 seconds",
    playback: "Slow motion · 60 fps",
    audio: "Silent",
    paragraphs: [
      "The fly takes on the roundabout. Get a closer look from inside the cabin as it works the indicator stalk, turns the wheel, and cancels the signal, with our sponsors riding on the Mini.",
      "This slow-motion cut gives each moment room to breathe, including contact with traffic. Navigation and speed are still engineered inputs; the experiment continues.",
    ],
    facts: [
      "Steering & indicator sequence",
      "Seven sponsors on the Mini",
      "25-second slow-motion cut",
    ],
    evidenceUrl:
      "https://github.com/MarkUnthank/flyhard/tree/main/reports/2026-09-10-roundabout-media",
    evidenceLabel: "Recording notes & video verification",
    stills: [
      {
        file: "roundabout-arrival.jpg",
        caption: "The sponsors arrive at the roundabout.",
      },
      {
        file: "roundabout-indicator.jpg",
        caption: "A closer look at the indicator.",
      },
      {
        file: "roundabout-cabin.jpg",
        caption: "Inside the cabin as the fly cancels the signal.",
      },
    ],
  },
  {
    id: "faster-steering",
    number: "02",
    date: "2026-09-09",
    dateLabel: "9 September 2026",
    category: "Steering experiment",
    title: "A little too much ambition.",
    intro: "Same tiny brain. A much faster request. This time, the road wins.",
    duration: "14 seconds",
    playback: "Normal simulation speed",
    audio: "Silent",
    paragraphs: [
      "We kept the learned steering controller and increased the scripted speed and turn requests. The model moves the fly’s left foreleg, the leg turns a passive wheel through an assisted grip, and the measured wheel angle steers the car.",
      "The result includes contact with a parked motorcycle and then a pole. This controller has no camera input or learned road awareness. It can follow steering requests; choosing safe requests from the road is still ahead.",
      "This is the first 14 seconds of a 24-second run, played at normal simulation speed. The stationary tail is omitted. The road, neural activity, and fly body all follow the same recorded clock.",
    ],
    facts: [
      "Same steering controller",
      "Scripted speed & turns",
      "Both collisions retained",
    ],
    evidenceUrl: `${evidence}/carla-new-yorker-v1`,
    evidenceLabel: "Faster run: metrics, validation & export details",
  },
  {
    id: "calm-steering",
    number: "01",
    date: "2026-09-09",
    dateLabel: "9 September 2026",
    category: "Steering experiment",
    title: "Small turns. A real start.",
    intro:
      "From a neural model to a moving leg, a turning wheel, and a car that follows.",
    duration: "24 seconds",
    playback: "Normal simulation speed",
    audio: "Silent",
    paragraphs: [
      "Our first calm recording puts the pieces side by side: the view from CARLA, the model’s neural activity, and the simulated fly at its wheel. The learned policy controls the left foreleg. The right foreleg follows the wheel through a passive supporting grip.",
      "In this run, the car travels 45.58 metres with no collisions. Replaying the saved neural actions reproduces the recorded joint positions and commands exactly. Disabling the grip reduces peak steering by more than 99.97%, helping establish that the leg-to-wheel connection causes the turn.",
      "Speed and requested turn angles are scripted. This demonstrates the recorded steering chain, rather than autonomous driving. The next challenge is learning what to do from what is on the road.",
    ],
    facts: [
      "600 recorded frames",
      "45.58 metres travelled",
      "0 collisions in this run",
    ],
    evidenceUrl: `${evidence}/carla-calm-v2`,
    evidenceLabel: "Calm run: metrics, validation & grip comparison",
  },
];
