from PIL import Image

from app.services.imaging import crop_image, dhash, hamming, remove_corner_background, resize_image
from app.services.metadata import build_metadata, validate_metadata


def test_corner_background_removal_keeps_the_subject():
    image = Image.new("RGBA", (48, 48), (240, 240, 240, 255))
    subject = Image.new("RGBA", (16, 16), (20, 40, 180, 255))
    image.paste(subject, (16, 16))
    cut = remove_corner_background(image, tolerance=12)
    assert cut.getpixel((0, 0))[3] == 0
    assert cut.getpixel((24, 24))[3] == 255
    assert cut.getpixel((24, 24))[:3] == (20, 40, 180)


def test_crop_and_resize():
    image = Image.new("RGBA", (40, 20), (255, 0, 0, 255))
    cropped = crop_image(image, 5, 5, 10, 8)
    assert cropped.size == (10, 8)
    resized = resize_image(cropped, 20, 20, "contain")
    assert resized.size == (20, 20)
    assert resized.getpixel((0, 0))[3] == 0


def test_identical_images_have_distance_zero():
    image = Image.new("RGBA", (32, 32), (10, 20, 30, 255))
    assert hamming(dhash(image), dhash(image)) == 0


def test_erc721_metadata_round_trip():
    body = build_metadata(
        collection_name="Signal",
        symbol="SIG",
        description_template="{collection} #{token_id} — {trait_list}",
        image_base_uri="ipfs://cid/{token_id}.png",
        external_url="",
        schema="erc721",
        token_id=4,
        attributes=[{"trait_type": "Background", "value": "Dusk"}],
        license_name="cc-by",
        ai_disclosure="",
    )
    assert validate_metadata(body, "erc721") == []
    assert body["image"] == "ipfs://cid/4.png"
    assert body["attributes"][0]["value"] == "Dusk"
    broken = dict(body)
    del broken["name"]
    assert validate_metadata(broken, "erc721")
