#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
#     "datasets",
#     "Pillow",
#     "torch",
#     "torchvision",
# ]
# ///
"""Seed the platform with default ImageNet-1K assets (REAL mode).

Requires ``datasets``, ``Pillow``, ``torch``, ``torchvision``, and
``HF_TOKEN`` env var with an accepted HuggingFace license for
``ILSVRC/imagenet-1k``.

Usage::

    HF_TOKEN=hf_... make seed-imagenet-real ARGS="--max-samples 200"

Creates:
  1. Dataset "ImageNet-1K" with full 1000-class label space.
  2. Preset "imagenet-resnet50".
  3. Real images streamed from HuggingFace ``ILSVRC/imagenet-1k``
     (validation split).
  4. Training job, then uploads real pretrained ResNet-50 weights
     (``torchvision`` ``ResNet50_Weights.IMAGENET1K_V2``) as model artifact.

Fully idempotent — re-running skips assets that already exist.

For lightweight dev/testing without extra deps, use
``scripts/seed_imagenet_dev.py`` (``make seed-imagenet-dev``).
"""

from __future__ import annotations

import argparse
import base64
import io
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

DATASET_NAME = "ImageNet-1K"
PRESET_NAME = "imagenet-resnet50"

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

PRESET_SPEC = {
    "name": PRESET_NAME,
    "model_spec": {
        "framework": "pytorch",
        "base_model": "resnet50",
    },
    "omegaconf_yaml": """# ResNet-50 ImageNet Classification
model:
  name: resnet50
  pretrained: true
  num_classes: 1000

training:
  epochs: 90
  batch_size: 256
  learning_rate: 0.1
  optimizer: SGD
  momentum: 0.9
  weight_decay: 0.0001

scheduler:
  name: StepLR
  step_size: 30
  gamma: 0.1

augment:
  resize: 256
  crop: 224
  horizontal_flip: true
  normalize:
    mean: [0.485, 0.456, 0.406]
    std: [0.229, 0.224, 0.225]
""",
    "dataloader_ref": "torchvision.datasets:ImageNet",
}


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


def _image_to_data_uri(img) -> str:
    """Convert a PIL Image to a JPEG data URI (used in --real mode)."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


# ---------------------------------------------------------------------------
# Sample creation helpers
# ---------------------------------------------------------------------------



def _create_real_samples(
    client: httpx.Client,
    dataset_id: str,
    max_samples: int,
    batch_report: int,
) -> int:
    """Stream real images from HuggingFace ``ILSVRC/imagenet-1k``."""
    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError:
        print("  ERROR: 'datasets' package not found. Install: uv pip install datasets Pillow")
        sys.exit(1)

    print("  Loading ILSVRC/imagenet-1k from HuggingFace (streaming) ...")
    print("  (Requires HF_TOKEN env var with accepted license)")
    hf = load_dataset("ILSVRC/imagenet-1k", split="validation", streaming=True)

    created = 0
    skipped = 0
    t0 = time.time()
    limit = max_samples if max_samples > 0 else float("inf")

    for example in hf:
        if created >= limit:
            break

        image = example["image"]
        label_idx = example["label"]
        data_uri = _image_to_data_uri(image)

        label_name = IMAGENET_LABELS[label_idx] if label_idx < len(IMAGENET_LABELS) else f"class_{label_idx}"
        metadata = {
            "source": "imagenet-1k",
            "split": "validation",
            "label_index": label_idx,
            "label_name": label_name,
        }

        r = _api(client, "post", f"/api/v1/datasets/{dataset_id}/samples", json={
            "image_uris": [data_uri],
            "metadata": metadata,
        })
        if r.status_code == 200:
            created += 1
        else:
            skipped += 1
            if skipped <= 3:
                print(f"    WARN: {r.status_code} {r.text[:120]}")

        if created > 0 and created % batch_report == 0:
            elapsed = time.time() - t0
            rate = created / elapsed if elapsed > 0 else 0
            print(f"    ... {created} samples ({rate:.1f}/s)")

    elapsed = time.time() - t0
    print(f"  Created {created} real samples, skipped {skipped} in {elapsed:.1f}s")
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


def _upload_real_resnet50(
    client: httpx.Client,
    job_id: str,
) -> str | None:
    """Download pretrained ResNet-50 weights and upload via /models/upload."""
    try:
        import torch  # type: ignore[import-untyped]
        from torchvision import models  # type: ignore[import-untyped]
    except ImportError:
        print("  ERROR: torch/torchvision not found. Install: uv pip install torch torchvision")
        return None

    print("  Downloading pretrained ResNet-50 weights ...")
    model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    model_bytes = buf.getvalue()
    print(f"  Model size: {len(model_bytes) / 1024 / 1024:.1f} MB")

    print("  Uploading to platform ...")
    r = client.post(
        "/api/v1/models/upload",
        params={"name": "resnet50-imagenet1k-v2", "format": "pytorch", "job_id": job_id},
        files={"file": ("resnet50_imagenet1k_v2.pt", io.BytesIO(model_bytes), "application/octet-stream")},
    )
    if r.status_code == 200:
        model_id = r.json()["id"]
        print(f"  Uploaded model: {model_id}")
        return model_id
    else:
        print(f"  ERROR: upload failed: {r.status_code} {r.text}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed default ImageNet-1K dataset, preset, and model (real mode)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Real mode (HuggingFace images, pretrained ResNet-50)
  HF_TOKEN=hf_... uv run python scripts/seed_imagenet_real.py --no-promote --max-samples 200
""",
    )
    parser.add_argument("--api-url", default="http://localhost:8000", help="Platform API base URL")
    parser.add_argument("--compose-file", default=COMPOSE_FILE, help="Docker compose file path")
    parser.add_argument("--no-promote", action="store_true", help="Skip superadmin promotion")
    parser.add_argument("--no-model", action="store_true", help="Skip model creation (dataset + preset only)")
    parser.add_argument("--no-samples", action="store_true", help="Skip sample creation")
    parser.add_argument("--max-samples", type=int, default=0,
                        help="Max samples to create (0 = stream all available)")
    parser.add_argument("--batch-report", type=int, default=100, help="Report progress every N samples")
    parser.add_argument("--job-timeout", type=int, default=60, help="Max seconds to wait for training job (default: 60)")
    args = parser.parse_args()

    max_samples = args.max_samples
    total_steps = 7 if not args.no_samples else 6
    print(f"\n{'=' * 50}")
    print(f"  ImageNet-1K Seed Script (real mode)")
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
    print(f"\n[5/{total_steps}] Creating/finding ImageNet-1K dataset ...")

    r = _api(client, "get", "/api/v1/datasets")
    existing_datasets = r.json() if r.status_code == 200 else []
    dataset = _find_by_name(existing_datasets, DATASET_NAME)
    dataset_id: str

    if dataset:
        dataset_id = dataset["id"]
        print(f"  Dataset already exists: {dataset_id}")
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
    print(f"\n[6/{total_steps}] Creating/finding training preset ...")

    r = _api(client, "get", "/api/v1/training-presets")
    existing_presets = r.json() if r.status_code == 200 else []
    preset = _find_by_name(existing_presets, PRESET_NAME)
    preset_id: str

    if preset:
        preset_id = preset["id"]
        print(f"  Preset already exists: {preset_id}")
    else:
        r = _api(client, "post", "/api/v1/training-presets", json=PRESET_SPEC)
        if r.status_code == 200:
            preset_id = r.json()["id"]
            print(f"  Created preset: {preset_id}")
        else:
            print(f"  ERROR: preset creation failed: {r.status_code} {r.text}")
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
            sample_count = _create_real_samples(client, dataset_id, max_samples, args.batch_report)

    # ------------------------------------------------------------------
    # Step 8: Create model
    # ------------------------------------------------------------------
    model_id: str | None = None
    job_id: str | None = None

    if args.no_model:
        print("\n  Skipping model creation (--no-model).")
    else:
        print("\n[model] Creating training job + model artifact ...")

        # Check if a model already exists for this dataset
        r = _api(client, "get", f"/api/v1/models?dataset_id={dataset_id}")
        if r.status_code == 200 and r.json():
            existing_model = r.json()[0]
            model_id = existing_model["id"]
            print(f"  Model already exists: {model_id} (name: {existing_model.get('name', 'n/a')})")
        else:
            # Need a training job first (model upload requires job_id)
            job_id, fake_model_id = _create_model_via_training_job(
                client, dataset_id, preset_id, args.job_timeout,
            )

            if job_id:
                # Upload real pretrained ResNet-50 weights (replaces the fake model)
                real_model_id = _upload_real_resnet50(client, job_id)
                model_id = real_model_id or fake_model_id
            else:
                model_id = fake_model_id

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print(f"  Seed Summary (real mode)")
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
