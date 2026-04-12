#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
# ]
# ///
"""Seed the platform with default ImageNet-1K mock assets.

No extra dependencies beyond ``httpx``.  No HuggingFace account required.

Usage::

    make seed-imagenet-mock
    make seed-imagenet-mock ARGS="--max-samples 50"

Creates:
  1. Dataset "ImageNet-1K Mock" with full 1000-class label space.
  2. Preset "imagenet-resnet50".
  3. Synthetic placeholder samples (coloured squares, one per class by
     default, capped by ``--max-samples``).
  4. Training job via the local engine -> fake model artifact.

Fully idempotent — re-running skips assets that already exist.

For real ImageNet data, use
``scripts/seed_imagenet_real.py`` (``make seed-imagenet-poc`` or ``make seed-imagenet-full``).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import random
import subprocess
import sys
import time

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED_EMAIL = "seed@example.com"
SEED_PASSWORD = "seed1234"
SEED_NAME = "Seed Admin"
ORG_NAME = "Default Org"
ORG_SLUG = "default-org"
COMPOSE_FILE = "infra/compose/docker-compose.yaml"

DATASET_NAME = "ImageNet-1K Mock"
LEGACY_DATASET_NAME = "ImageNet-1K"
PRESET_ID = "resnet50-cls-v1"
PRESET_NAME = "ResNet50 Classification (v1)"
PLACEHOLDER_MODEL_NAME = "imagenet-mock-placeholder"
SEED_MODE = "mock"

# Full ImageNet-1K class list (ILSVRC 2012, 1000 classes)
# Source: https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt
IMAGENET_LABELS: list[str] = [
    "tench", "goldfish", "great white shark", "tiger shark", "hammerhead",
    "electric ray", "stingray", "cock", "hen", "ostrich",
    "brambling", "goldfinch", "house finch", "junco", "indigo bunting",
    "robin", "bulbul", "jay", "magpie", "chickadee",
    "water ouzel", "kite", "bald eagle", "vulture", "great grey owl",
    "European fire salamander", "common newt", "eft", "spotted salamander", "axolotl",
    "bullfrog", "tree frog", "tailed frog", "loggerhead", "leatherback turtle",
    "mud turtle", "terrapin", "box turtle", "banded gecko", "common iguana",
    "American chameleon", "whiptail", "agama", "frilled lizard", "alligator lizard",
    "Gila monster", "green lizard", "African chameleon", "Komodo dragon", "African crocodile",
    "American alligator", "triceratops", "thunder snake", "ringneck snake", "hognose snake",
    "green snake", "king snake", "garter snake", "water snake", "vine snake",
    "night snake", "boa constrictor", "rock python", "Indian cobra", "green mamba",
    "sea snake", "horned viper", "diamondback", "sidewinder", "trilobite",
    "harvestman", "scorpion", "black and gold garden spider", "barn spider", "garden spider",
    "black widow", "tarantula", "wolf spider", "tick", "centipede",
    "black grouse", "ptarmigan", "ruffed grouse", "prairie chicken", "peacock",
    "quail", "partridge", "African grey", "macaw", "sulphur-crested cockatoo",
    "lorikeet", "coucal", "bee eater", "hornbill", "hummingbird",
    "jacamar", "toucan", "drake", "red-breasted merganser", "goose",
    "black swan", "tusker", "echidna", "platypus", "wallaby",
    "koala", "wombat", "jellyfish", "sea anemone", "brain coral",
    "flatworm", "nematode", "conch", "snail", "slug",
    "sea slug", "chiton", "chambered nautilus", "Dungeness crab", "rock crab",
    "fiddler crab", "king crab", "American lobster", "spiny lobster", "crayfish",
    "hermit crab", "isopod", "white stork", "black stork", "spoonbill",
    "flamingo", "little blue heron", "American egret", "bittern", "crane",
    "limpkin", "European gallinule", "American coot", "bustard", "ruddy turnstone",
    "red-backed sandpiper", "redshank", "dowitcher", "oystercatcher", "pelican",
    "king penguin", "albatross", "grey whale", "killer whale", "dugong",
    "sea lion", "Chihuahua", "Japanese spaniel", "Maltese dog", "Pekinese",
    "Shih-Tzu", "Blenheim spaniel", "papillon", "toy terrier", "Rhodesian ridgeback",
    "Afghan hound", "basset", "beagle", "bloodhound", "bluetick",
    "black-and-tan coonhound", "Walker hound", "English foxhound", "redbone", "borzoi",
    "Irish wolfhound", "Italian greyhound", "whippet", "Ibizan hound", "Norwegian elkhound",
    "otterhound", "Saluki", "Scottish deerhound", "Weimaraner", "Staffordshire bullterrier",
    "American Staffordshire terrier", "Bedlington terrier", "Border terrier", "Kerry blue terrier", "Irish terrier",
    "Norfolk terrier", "Norwich terrier", "Yorkshire terrier", "wire-haired fox terrier", "Lakeland terrier",
    "Sealyham terrier", "Airedale", "cairn", "Australian terrier", "Dandie Dinmont",
    "Boston bull", "miniature schnauzer", "giant schnauzer", "standard schnauzer", "Scotch terrier",
    "Tibetan terrier", "silky terrier", "soft-coated wheaten terrier", "West Highland white terrier", "Lhasa",
    "flat-coated retriever", "curly-coated retriever", "golden retriever", "Labrador retriever", "Chesapeake Bay retriever",
    "German short-haired pointer", "vizsla", "English setter", "Irish setter", "Gordon setter",
    "Brittany spaniel", "clumber", "English springer", "Welsh springer spaniel", "cocker spaniel",
    "Sussex spaniel", "Irish water spaniel", "kuvasz", "schipperke", "groenendael",
    "malinois", "briard", "kelpie", "komondor", "Old English sheepdog",
    "Shetland sheepdog", "collie", "Border collie", "Bouvier des Flandres", "Rottweiler",
    "German shepherd", "Doberman", "miniature pinscher", "Greater Swiss Mountain dog", "Bernese mountain dog",
    "Appenzeller", "EntleBucher", "boxer", "bull mastiff", "Tibetan mastiff",
    "French bulldog", "Great Dane", "Saint Bernard", "Eskimo dog", "malamute",
    "Siberian husky", "dalmatian", "affenpinscher", "basenji", "pug",
    "Leonberg", "Newfoundland", "Great Pyrenees", "Samoyed", "Pomeranian",
    "chow", "keeshond", "Brabancon griffon", "Pembroke", "Cardigan",
    "toy poodle", "miniature poodle", "standard poodle", "Mexican hairless", "timber wolf",
    "white wolf", "red wolf", "coyote", "dingo", "dhole",
    "African hunting dog", "hyena", "red fox", "kit fox", "Arctic fox",
    "grey fox", "tabby", "tiger cat", "Persian cat", "Siamese cat",
    "Egyptian cat", "cougar", "lynx", "leopard", "snow leopard",
    "jaguar", "lion", "tiger", "cheetah", "brown bear",
    "American black bear", "ice bear", "sloth bear", "mongoose", "meerkat",
    "tiger beetle", "ladybug", "ground beetle", "long-horned beetle", "leaf beetle",
    "dung beetle", "rhinoceros beetle", "weevil", "fly", "bee",
    "ant", "grasshopper", "cricket", "walking stick", "cockroach",
    "mantis", "cicada", "leafhopper", "lacewing", "dragonfly",
    "damselfly", "admiral", "ringlet", "monarch", "cabbage butterfly",
    "sulphur butterfly", "lycaenid", "starfish", "sea urchin", "sea cucumber",
    "wood rabbit", "hare", "Angora", "hamster", "porcupine",
    "fox squirrel", "marmot", "beaver", "guinea pig", "sorrel",
    "zebra", "hog", "wild boar", "warthog", "hippopotamus",
    "ox", "water buffalo", "bison", "ram", "bighorn",
    "ibex", "hartebeest", "impala", "gazelle", "Arabian camel",
    "llama", "weasel", "mink", "polecat", "black-footed ferret",
    "otter", "skunk", "badger", "armadillo", "three-toed sloth",
    "orangutan", "gorilla", "chimpanzee", "gibbon", "siamang",
    "guenon", "patas", "baboon", "macaque", "langur",
    "colobus", "proboscis monkey", "marmoset", "capuchin", "howler monkey",
    "titi", "spider monkey", "squirrel monkey", "Madagascar cat", "indri",
    "Indian elephant", "African elephant", "lesser panda", "giant panda", "barracouta",
    "eel", "coho", "rock beauty", "anemone fish", "sturgeon",
    "gar", "lionfish", "puffer", "abacus", "abaya",
    "academic gown", "accordion", "acoustic guitar", "aircraft carrier", "airliner",
    "airship", "altar", "ambulance", "amphibian", "analog clock",
    "apiary", "apron", "ashcan", "assault rifle", "backpack",
    "bakery", "balance beam", "balloon", "ballpoint", "Band Aid",
    "banjo", "bannister", "barbell", "barber chair", "barbershop",
    "barn", "barometer", "barrel", "barrow", "baseball",
    "basketball", "bassinet", "bassoon", "bathing cap", "bath towel",
    "bathtub", "beach wagon", "beacon", "beaker", "bearskin",
    "beer bottle", "beer glass", "bell cote", "bib", "bicycle-built-for-two",
    "bikini", "binder", "binoculars", "birdhouse", "boathouse",
    "bobsled", "bolo tie", "bonnet", "bookcase", "bookshop",
    "bottlecap", "bow", "bow tie", "brass", "brassiere",
    "breakwater", "breastplate", "broom", "bucket", "buckle",
    "bulletproof vest", "bullet train", "butcher shop", "cab", "caldron",
    "candle", "cannon", "canoe", "can opener", "cardigan",
    "car mirror", "carousel", "carpenter's kit", "carton", "car wheel",
    "cash machine", "cassette", "cassette player", "castle", "catamaran",
    "CD player", "cello", "cellular telephone", "chain", "chainlink fence",
    "chain mail", "chain saw", "chest", "chiffonier", "chime",
    "china cabinet", "Christmas stocking", "church", "cinema", "cleaver",
    "cliff dwelling", "cloak", "clog", "cocktail shaker", "coffee mug",
    "coffeepot", "coil", "combination lock", "computer keyboard", "confectionery",
    "container ship", "convertible", "corkscrew", "cornet", "cowboy boot",
    "cowboy hat", "cradle", "crane", "crash helmet", "crate",
    "crib", "Crock Pot", "croquet ball", "crutch", "cuirass",
    "dam", "desk", "desktop computer", "dial telephone", "diaper",
    "digital clock", "digital watch", "dining table", "dishrag", "dishwasher",
    "disk brake", "dock", "dogsled", "dome", "doormat",
    "drilling platform", "drum", "drumstick", "dumbbell", "Dutch oven",
    "electric fan", "electric guitar", "electric locomotive", "entertainment center", "envelope",
    "espresso maker", "face powder", "feather boa", "file", "fireboat",
    "fire engine", "fire screen", "flagpole", "flute", "folding chair",
    "football helmet", "forklift", "fountain", "fountain pen", "four-poster",
    "freight car", "French horn", "frying pan", "fur coat", "garbage truck",
    "gasmask", "gas pump", "goblet", "go-kart", "golf ball",
    "golfcart", "gondola", "gong", "gown", "grand piano",
    "greenhouse", "grille", "grocery store", "guillotine", "hair slide",
    "hair spray", "half track", "hammer", "hamper", "hand blower",
    "hand-held computer", "handkerchief", "hard disc", "harmonica", "harp",
    "harvester", "hatchet", "holster", "home theater", "honeycomb",
    "hook", "hoopskirt", "horizontal bar", "horse cart", "hourglass",
    "iPod", "iron", "jack-o'-lantern", "jean", "jeep",
    "jersey", "jigsaw puzzle", "jinrikisha", "joystick", "kimono",
    "knee pad", "knot", "lab coat", "ladle", "lampshade",
    "laptop", "lawn mower", "lens cap", "letter opener", "library",
    "lifeboat", "lighter", "limousine", "liner", "lipstick",
    "Loafer", "lotion", "loudspeaker", "loupe", "lumbermill",
    "magnetic compass", "mailbag", "mailbox", "maillot", "maillot",
    "manhole cover", "maraca", "marimba", "mask", "matchstick",
    "maypole", "maze", "measuring cup", "medicine chest", "megalith",
    "microphone", "microwave", "military uniform", "milk can", "minibus",
    "miniskirt", "minivan", "missile", "mitten", "mixing bowl",
    "mobile home", "Model T", "modem", "monastery", "monitor",
    "moped", "mortar", "mortarboard", "mosque", "mosquito net",
    "motor scooter", "mountain bike", "mountain tent", "mouse", "mousetrap",
    "moving van", "muzzle", "nail", "neck brace", "necklace",
    "nipple", "notebook", "obelisk", "oboe", "ocarina",
    "odometer", "oil filter", "organ", "oscilloscope", "overskirt",
    "oxcart", "oxygen mask", "packet", "paddle", "paddlewheel",
    "padlock", "paintbrush", "pajama", "palace", "panpipe",
    "paper towel", "parachute", "parallel bars", "park bench", "parking meter",
    "passenger car", "patio", "pay-phone", "pedestal", "pencil box",
    "pencil sharpener", "perfume", "Petri dish", "photocopier", "pick",
    "pickelhaube", "picket fence", "pickup", "pier", "piggy bank",
    "pill bottle", "pillow", "ping-pong ball", "pinwheel", "pirate",
    "pitcher", "plane", "planetarium", "plastic bag", "plate rack",
    "plow", "plunger", "Polaroid camera", "pole", "police van",
    "poncho", "pool table", "pop bottle", "pot", "potter's wheel",
    "power drill", "prayer rug", "printer", "prison", "projectile",
    "projector", "puck", "punching bag", "purse", "quill",
    "quilt", "racer", "racket", "radiator", "radio",
    "radio telescope", "rain barrel", "recreational vehicle", "reel", "reflex camera",
    "refrigerator", "remote control", "restaurant", "revolver", "rifle",
    "rocking chair", "rotisserie", "rubber eraser", "rugby ball", "rule",
    "running shoe", "safe", "safety pin", "saltshaker", "sandal",
    "sarong", "sax", "scabbard", "scale", "school bus",
    "schooner", "scoreboard", "screen", "screw", "screwdriver",
    "seat belt", "sewing machine", "shield", "shoe shop", "shoji",
    "shopping basket", "shopping cart", "shovel", "shower cap", "shower curtain",
    "ski", "ski mask", "sleeping bag", "slide rule", "sliding door",
    "slot", "snorkel", "snowmobile", "snowplow", "soap dispenser",
    "soccer ball", "sock", "solar dish", "sombrero", "soup bowl",
    "space bar", "space heater", "space shuttle", "spatula", "speedboat",
    "spider web", "spindle", "sports car", "spotlight", "stage",
    "steam locomotive", "steel arch bridge", "steel drum", "stethoscope", "stole",
    "stone wall", "stopwatch", "stove", "strainer", "streetcar",
    "stretcher", "studio couch", "stupa", "submarine", "suit",
    "sundial", "sunglass", "sunglasses", "sunscreen", "suspension bridge",
    "swab", "sweatshirt", "swimming trunks", "swing", "switch",
    "syringe", "table lamp", "tank", "tape player", "teapot",
    "teddy", "television", "tennis ball", "thatch", "theater curtain",
    "thimble", "thresher", "throne", "tile roof", "toaster",
    "tobacco shop", "toilet seat", "torch", "totem pole", "tow truck",
    "toyshop", "tractor", "trailer truck", "tray", "trench coat",
    "tricycle", "trimaran", "tripod", "triumphal arch", "trolleybus",
    "trombone", "tub", "turnstile", "typewriter keyboard", "umbrella",
    "unicycle", "upright", "vacuum", "vase", "vault",
    "velvet", "vending machine", "vestment", "viaduct", "violin",
    "volleyball", "waffle iron", "wall clock", "wallet", "wardrobe",
    "warplane", "washbasin", "washer", "water bottle", "water jug",
    "water tower", "whiskey jug", "whistle", "wig", "window screen",
    "window shade", "Windsor tie", "wine bottle", "wing", "wok",
    "wooden spoon", "wool", "worm fence", "wreck", "yawl",
    "yurt", "web site", "comic book", "crossword puzzle", "street sign",
    "traffic light", "book jacket", "menu", "plate", "guacamole",
    "consomme", "hot pot", "trifle", "ice cream", "ice lolly",
    "French loaf", "bagel", "pretzel", "cheeseburger", "hotdog",
    "mashed potato", "head cabbage", "broccoli", "cauliflower", "zucchini",
    "spaghetti squash", "acorn squash", "butternut squash", "cucumber", "artichoke",
    "bell pepper", "cardoon", "mushroom", "Granny Smith", "strawberry",
    "orange", "lemon", "fig", "pineapple", "banana",
    "jackfruit", "custard apple", "pomegranate", "hay", "carbonara",
    "chocolate sauce", "dough", "meat loaf", "pizza", "potpie",
    "burrito", "red wine", "espresso", "cup", "eggnog",
    "alp", "bubble", "cliff", "coral reef", "geyser",
    "lakeside", "promontory", "sandbar", "seashore", "valley",
    "volcano", "ballplayer", "groom", "scuba diver", "rapeseed",
    "daisy", "yellow lady's slipper", "corn", "acorn", "hip",
    "buckeye", "coral fungus", "agaric", "gyromitra", "stinkhorn",
    "earthstar", "hen-of-the-woods", "bolete", "ear", "toilet tissue",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    return getattr(client, method)(path, **kwargs)


def _promote_superadmin(compose_file: str) -> None:
    cmd = [
        "docker", "compose", "-f", compose_file,
        "exec", "-T", "api",
        "uv", "run", "python", "-m", "app.cli",
        "create-superadmin",
        f"--email={SEED_EMAIL}",
        f"--password={SEED_PASSWORD}",
        f"--name={SEED_NAME}",
    ]
    print(f"  Promoting {SEED_EMAIL} to superadmin via docker exec ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING: promote failed (rc={result.returncode}): {result.stderr.strip()}")
        print("  If running locally, use: make create-superadmin EMAIL=seed@example.com PASSWORD=seed1234 NAME='Seed Admin'")
    else:
        print(f"  {result.stdout.strip()}")


def _find_by_name(items: list[dict], name: str) -> dict | None:
    for item in items:
        if item.get("name") == name:
            return item
    return None


def _delete_model(client: httpx.Client, model_id: str) -> None:
    r = _api(client, "delete", f"/api/v1/models/{model_id}")
    if r.status_code != 204:
        raise RuntimeError(f"failed to delete existing model {model_id}: {r.status_code} {r.text}")


def _find_conflicting_legacy_dataset(items: list[dict]) -> dict | None:
    return _find_by_name(items, LEGACY_DATASET_NAME)


def _is_image_classification_compatible(model: dict) -> bool:
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    dataset_types = metadata.get("dataset_types") if isinstance(metadata.get("dataset_types"), list) else []
    task_types = metadata.get("task_types") if isinstance(metadata.get("task_types"), list) else []
    prediction_targets = metadata.get("prediction_targets") if isinstance(metadata.get("prediction_targets"), list) else []
    return (
        "image_classification" in dataset_types
        and "classification" in task_types
        and "image_classification" in prediction_targets
    )


def _generate_synthetic_image(label: str, index: int, size: int = 224) -> str:
    """Generate a simple colored PNG with the label text burned in.

    Returns a ``data:image/png;base64,...`` data URI.  Uses only the stdlib
    (``zlib`` for PNG compression) so no Pillow dependency is needed in
    dev mode.
    """
    # Deterministic colour from the class index
    rng = random.Random(index)
    r, g, b = rng.randint(40, 220), rng.randint(40, 220), rng.randint(40, 220)

    # Build raw RGBA rows (unfiltered PNG scanlines)
    raw_rows = bytearray()
    for _y in range(size):
        raw_rows.append(0)  # PNG filter byte: None
        for _x in range(size):
            raw_rows.extend((r, g, b))

    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr_data = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(raw_rows), 6)

    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr_data)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")

    b64 = base64.b64encode(png).decode()
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Sample creation helpers
# ---------------------------------------------------------------------------


def _create_synthetic_samples(
    client: httpx.Client,
    dataset_id: str,
    max_samples: int,
    batch_report: int,
) -> int:
    """Create synthetic coloured-square samples, one per class up to max_samples."""
    count = min(max_samples, len(IMAGENET_LABELS))
    print(f"  Generating {count} synthetic samples (coloured squares) ...")

    created = 0
    batch_size = 5000
    t0 = time.time()
    batch: list[dict] = []
    for idx in range(count):
        label = IMAGENET_LABELS[idx]
        data_uri = _generate_synthetic_image(label, idx)
        metadata = {
            "source": "synthetic",
            "label_index": idx,
            "label_name": label,
        }
        batch.append({"image_uris": [data_uri], "metadata": metadata})

        if len(batch) >= batch_size or idx == count - 1:
            r = _api(client, "post", f"/api/v1/datasets/{dataset_id}/samples/import", json={"items": batch})
            if r.status_code == 200:
                created += int(r.json().get("imported", 0))
            else:
                print(f"    WARN batch ending at sample {idx}: {r.status_code} {r.text[:120]}")
            batch = []

        if created > 0 and created % batch_report == 0:
            elapsed = time.time() - t0
            rate = created / elapsed if elapsed > 0 else 0
            print(f"    ... {created}/{count} samples ({rate:.1f}/s)")

    elapsed = time.time() - t0
    print(f"  Created {created} synthetic samples in {elapsed:.1f}s")
    return created


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------


def _create_model_via_training_job(
    client: httpx.Client,
    dataset_id: str,
    preset_id: str,
    job_timeout: int,
) -> tuple[str | None, str | None]:
    """Create a training job via local engine and return (job_id, model_id)."""
    r = _api(client, "post", "/api/v1/training-jobs", json={
        "dataset_id": dataset_id,
        "preset_id": preset_id,
    })
    if r.status_code != 200:
        print(f"  ERROR: job creation failed: {r.status_code} {r.text}")
        return None, None
    job_id = r.json()["id"]
    print(f"  Job created: {job_id}, waiting for completion ...")

    t0 = time.time()
    while time.time() - t0 < job_timeout:
        r = _api(client, "get", f"/api/v1/training-jobs/{job_id}")
        if r.status_code == 200:
            status = r.json().get("status", "")
            if status == "completed":
                print(f"  Job completed in {time.time() - t0:.1f}s")
                break
            if status in ("failed", "cancelled"):
                print(f"  ERROR: job ended with status '{status}'")
                return job_id, None
        time.sleep(1)
    else:
        print(f"  ERROR: job did not complete within {job_timeout}s")
        return job_id, None

    r = _api(client, "get", f"/api/v1/models?dataset_id={dataset_id}")
    if r.status_code == 200 and r.json():
        model_id = r.json()[0]["id"]
        return job_id, model_id
    return job_id, None


def _upload_placeholder_model(
    client: httpx.Client,
    job_id: str,
    label_space: list[str],
) -> str | None:
    dim = 64
    label_prototypes: dict[str, list[float]] = {}
    for idx, label in enumerate(label_space):
        vec = [0.0] * dim
        vec[idx % dim] = 1.0
        label_prototypes[label] = vec
    metadata = {
        "name": PLACEHOLDER_MODEL_NAME,
        "seed_mode": SEED_MODE,
        "format": "pytorch",
        "job_id": job_id,
        "template_id": "image-classifier",
        "profile_id": "resnet50-cls-v1",
        "model_spec": {
            "framework": "pytorch",
            "architecture": "resnet50",
            "base_model": "torchvision/resnet50",
        },
        "compatibility": {
            "dataset_types": ["image_classification"],
            "task_types": ["classification"],
            "prediction_targets": ["image_classification"],
            "label_space": label_space,
        },
    }
    payload = {
        "framework": "pytorch",
        "architecture": "resnet50",
        "label_space": label_space,
        "label_prototypes": label_prototypes,
        "source": "seed-imagenet-mock-placeholder",
    }
    files = {
        "file": (
            f"{PLACEHOLDER_MODEL_NAME}.pt",
            io.BytesIO(json.dumps(payload).encode("utf-8")),
            "application/octet-stream",
        ),
    }
    data = {"metadata": json.dumps(metadata)}
    r = client.post("/api/v1/models/upload", data=data, files=files)
    if r.status_code != 200:
        print(f"  ERROR: placeholder model upload failed: {r.status_code} {r.text}")
        return None
    model_id = r.json().get("id")
    print(f"  Uploaded placeholder image-classifier model: {model_id}")
    return model_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed ImageNet-1K mock dataset, preset, and model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dev mode (synthetic samples, fake model, no extra deps)
  uv run python scripts/seed_imagenet_dev.py --no-promote

  # Dev mode, fewer samples
  uv run python scripts/seed_imagenet_dev.py --no-promote --max-samples 50
""",
    )
    parser.add_argument("--api-url", default="http://localhost:8000", help="Platform API base URL")
    parser.add_argument("--compose-file", default=COMPOSE_FILE, help="Docker compose file path")
    parser.add_argument("--no-promote", action="store_true", help="Skip superadmin promotion")
    parser.add_argument("--no-model", action="store_true", help="Skip model creation (dataset + preset only)")
    parser.add_argument("--no-samples", action="store_true", help="Skip sample creation")
    parser.add_argument("--max-samples", type=int, default=1000,
                        help="Max samples to create (default: 1000, one per class)")
    parser.add_argument("--batch-report", type=int, default=100, help="Report progress every N samples")
    parser.add_argument("--job-timeout", type=int, default=60, help="Max seconds to wait for training job (default: 60)")
    args = parser.parse_args()

    max_samples = args.max_samples
    total_steps = 7 if not args.no_samples else 6
    print(f"\n{'=' * 50}")
    print(f"  ImageNet-1K Mock Seed Script")
    print(f"{'=' * 50}\n")

    api_url = args.api_url.rstrip("/")
    client = httpx.Client(base_url=api_url, timeout=30.0)

    # ------------------------------------------------------------------
    # Step 1: Register seed user
    # ------------------------------------------------------------------
    print(f"[1/{total_steps}] Registering seed user ...")
    r = _api(client, "post", "/api/v1/auth/register", json={
        "email": SEED_EMAIL,
        "password": SEED_PASSWORD,
        "name": SEED_NAME,
    })
    if r.status_code == 201:
        print(f"  Created user: {SEED_EMAIL}")
    elif r.status_code == 409:
        print("  User already exists, skipping.")
    else:
        print(f"  Warning: register returned {r.status_code}: {r.text}")

    # ------------------------------------------------------------------
    # Step 2: Promote to superadmin
    # ------------------------------------------------------------------
    print(f"\n[2/{total_steps}] Promoting to superadmin ...")
    if args.no_promote:
        print("  Skipped (--no-promote).")
    else:
        _promote_superadmin(args.compose_file)

    # ------------------------------------------------------------------
    # Step 3: Login
    # ------------------------------------------------------------------
    print(f"\n[3/{total_steps}] Logging in ...")
    r = _api(client, "post", "/api/v1/auth/login", json={
        "email": SEED_EMAIL,
        "password": SEED_PASSWORD,
    })
    if r.status_code != 200:
        print(f"  ERROR: login failed: {r.status_code} {r.text}")
        return 1
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print("  Logged in.")

    # ------------------------------------------------------------------
    # Step 4: Get or create organization
    # ------------------------------------------------------------------
    print(f"\n[4/{total_steps}] Getting/creating organization ...")
    r = _api(client, "get", "/api/v1/organizations")
    orgs = r.json() if r.status_code == 200 else []
    org_id = None
    for org in orgs:
        if org.get("slug") == ORG_SLUG or org.get("name") == ORG_NAME:
            org_id = org["id"]
            print(f"  Found existing org: {org_id}")
            break

    if not org_id:
        r = _api(client, "post", "/api/v1/organizations", json={"name": ORG_NAME, "slug": ORG_SLUG})
        if r.status_code in (200, 201):
            org_id = r.json()["id"]
            print(f"  Created org: {org_id}")
        else:
            print(f"  Warning: could not create org: {r.status_code} {r.text}")
            if orgs:
                org_id = orgs[0]["id"]
                print(f"  Using first available org: {org_id}")

    if org_id:
        client.headers["X-Organization-ID"] = org_id

    # ------------------------------------------------------------------
    # Step 5: Create or find dataset
    # ------------------------------------------------------------------
        print(f"\n[5/{total_steps}] Creating/finding {DATASET_NAME} dataset ...")

    r = _api(client, "get", "/api/v1/datasets")
    existing_datasets = r.json() if r.status_code == 200 else []
    legacy_dataset = _find_conflicting_legacy_dataset(existing_datasets)
    if legacy_dataset is not None:
        print(
            f"  ERROR: legacy dataset '{LEGACY_DATASET_NAME}' still exists ({legacy_dataset['id']}). "
            f"Remove or rename it before seeding {DATASET_NAME}."
        )
        return 1
    dataset = _find_by_name(existing_datasets, DATASET_NAME)
    dataset_id: str

    if dataset:
        dataset_id = dataset["id"]
        print(f"  Dataset already exists for mock seed: {dataset_id}")
        current_labels = dataset.get("task_spec", {}).get("label_space", [])
        if len(current_labels) != len(IMAGENET_LABELS):
            print(f"  Updating label space ({len(current_labels)} -> {len(IMAGENET_LABELS)} labels) ...")
            r = _api(client, "patch", f"/api/v1/datasets/{dataset_id}/label-space", json={
                "label_space": IMAGENET_LABELS,
            })
            if r.status_code == 200:
                print("  Label space updated.")
            else:
                print(f"  Warning: label space update failed: {r.status_code} {r.text}")
    else:
        r = _api(client, "post", "/api/v1/datasets", json={
            "name": DATASET_NAME,
            "dataset_type": "image_classification",
            "task_spec": {
                "task_type": "classification",
                "label_space": IMAGENET_LABELS,
            },
        })
        if r.status_code == 200:
            dataset_id = r.json()["id"]
            print(f"  Created dataset: {dataset_id} (LS project: {r.json().get('ls_project_id')})")
        else:
            print(f"  ERROR: dataset creation failed: {r.status_code} {r.text}")
            return 1

    # ------------------------------------------------------------------
    # Step 6: Create or find preset
    # ------------------------------------------------------------------
    print(f"\n[6/{total_steps}] Resolving training preset ...")

    r = _api(client, "get", "/api/v1/training-presets")
    existing_presets = r.json() if r.status_code == 200 else []
    preset = None
    for item in existing_presets:
        if item.get("id") == PRESET_ID or item.get("name") == PRESET_NAME:
            preset = item
            break
    preset_id: str

    if preset:
        preset_id = preset["id"]
        print(f"  Using preset: {preset_id} ({preset.get('name', 'unknown')})")
    else:
        print(f"  ERROR: required preset '{PRESET_ID}' is not available from /api/v1/training-presets")
        print("  Presets are file-backed and read-only; make sure the API started with the bundled preset registry.")
        return 1

    # ------------------------------------------------------------------
    # Step 7: Create samples
    # ------------------------------------------------------------------
    sample_count = 0
    if args.no_samples:
        print("\n  Skipping sample creation (--no-samples).")
    else:
        print(f"\n[7/{total_steps}] Creating samples ...")

        # Check if samples already exist
        r = _api(client, "get", f"/api/v1/datasets/{dataset_id}/samples?offset=0&limit=1")
        existing_total = r.json().get("total", 0) if r.status_code == 200 else 0
        if existing_total > 0:
            print(f"  Dataset already has {existing_total} samples, skipping.")
            sample_count = existing_total
        else:
            sample_count = _create_synthetic_samples(client, dataset_id, max_samples, args.batch_report)

    # ------------------------------------------------------------------
    # Step 8: Create model
    # ------------------------------------------------------------------
    model_id: str | None = None
    job_id: str | None = None

    if args.no_model:
        print("\n  Skipping model creation (--no-model).")
    else:
        print("\n[model] Creating training job + model artifact ...")

        # Replace any previous mock-seed models for this dataset so reruns converge
        r = _api(client, "get", f"/api/v1/models?dataset_id={dataset_id}")
        if r.status_code == 200:
            compatible_models = [model for model in r.json() if _is_image_classification_compatible(model)]
        else:
            compatible_models = []
        for existing_model in compatible_models:
            print(f"  Deleting existing mock model: {existing_model['id']} ({existing_model.get('name', 'n/a')})")
            _delete_model(client, existing_model["id"])
        job_id, model_id = _create_model_via_training_job(
            client, dataset_id, preset_id, args.job_timeout,
        )
        if model_id is None and job_id is not None:
            print("  Training job failed in dev mode; uploading placeholder image-classifier model instead ...")
            model_id = _upload_placeholder_model(client, job_id, IMAGENET_LABELS)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print(f"  Seed Summary (mock mode)")
    print(f"{'=' * 50}")
    print(f"  Dataset:    {DATASET_NAME}")
    print(f"  Dataset ID: {dataset_id}")
    print(f"  Labels:     {len(IMAGENET_LABELS)} ImageNet-1K classes")
    print(f"  Samples:    {sample_count}")
    print(f"  Preset:     {PRESET_NAME}")
    print(f"  Preset ID:  {preset_id}")
    if job_id:
        print(f"  Job ID:     {job_id}")
    if model_id:
        print(f"  Model ID:   {model_id}")
    print(f"{'=' * 50}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
