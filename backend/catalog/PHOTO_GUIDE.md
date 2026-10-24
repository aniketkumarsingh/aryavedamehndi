# Catalog photo guide

The design catalog shows customers a real photo of every design, and the
finished mehndi is checked against that photo. A design without a good
photo is hidden. This guide is for whoever takes the photos - our artists
or a photographer.

## Photos we still need

| Category | Design | What the photo must show |
|---|---|---|
| Bridal | Minimal Modern Bride | Both hands of a bride: a mandala on each palm with finger bands. Finished stain, plain background. |
| Bridal | Arabic Bridal Full Hand | Back of both hands and arms, fingertips to elbow, Arabic style. Finished stain. |
| Bridal | Peacock Bridal Full Hand | Both palms up, fingertips to elbow, with clear peacock motifs. Finished stain. |
| Festival | Karwa Chauth Moon & Chalni | Palm design with a clear moon, chalni and karwa pot. Finished stain. |
| Festival | Teej Jhoola & Leaves | Hand with a swing (jhoola) and leaves clearly drawn. Finished stain. |
| Festival | Diwali Diya & Rangoli | Palm with a clear diya and rangoli motifs, hand filling the photo. |
| Festival | Navratri Dandiya & Garba | Palm with clear garba dancer figures and crossed dandiya sticks. Finished stain. |
| Festival | Gangaur Isar & Gauri | Palm with Gauri (and Isar) figures and a kalash in Rajasthani style. Finished stain. |
| Festival | Ganesha & Modak Palm | Palm with a clear Ganesha figure in the centre. Finished stain. |
| Festival | Eid Lantern & Crescent | Back of hand with a clear hanging lantern and crescent, Arabic style. Finished stain. |
| Festival | Rakhi Thread & Thali | Palm and wrist with a rakhi drawn at the wrist and a small thali or diya on the palm. Finished stain. |
| Festival | Kites & Bonfire | Back of hand with clear kites and strings, plus a bonfire or sun motif. Finished stain. |
| Bridal | Nikah Arabic Jaal Bridal | Both hands, fingertips past the wrist, Arabic florals with jaal panels. Finished stain. |
| Party & Festive | Haldi Day Light Arabic | Back of hand with a light Arabic floral trail and finger tips. Finished stain. |
| Party & Festive | Roka Ring & Initials | Palm with a ring motif and made-up initials in a heart. Finished stain. |
| Party & Festive | Godh Bharai Mom & Baby | Palm with a mother-to-be figure and baby motifs (feet or cradle). Finished stain. |
| Party & Festive | Anniversary Couple & Hearts | Palm with a couple figure and hearts. Finished stain, no real names. |
| Kids | Birthday Cake & Balloons | A child's palm (no face) with a cake and balloons. Finished stain. |
| Party & Festive | Moroccan Geometric Back Hand | Back of hand in geometric Moroccan style. Finished stain. |
| Party & Festive | Shaded Rose Back Hand | Back of hand with shaded roses. Finished stain. |
| Feet | Classic Dipped Toes | Feet with henna-dipped toe tips - henna stain, not alta or nail polish. |
| Feet | Side Foot Jaali | Feet from the side or above, toes to ankle, dense jaali and florals. Sharp photo, no artist or props in the frame. *(old photo was out of focus)* |
| Kids | Little Palm Flower | A child's palm (no face) with one small flower in the middle. No smudges, plain background. *(old photo was grainy and smudged)* |
| Kids | Butterfly & Star | A child's hand (no face in the photo) with a butterfly design. |
| Groom (Dulha) | Minimal Palm Tikki | A man's palm with one round tikki. Finished stain, sharp photo. |
| Groom (Dulha) | Initials & Shagun | A man's palm with the couple's initials in a frame - use made-up initials, not real names. |
| Groom (Dulha) | Sehra Motif | A man's palm with a sehra or doli motif. Finished stain. |

### Close-ups we still need

These designs are shown, but their close-ups were too soft and were taken
out. A sharp main photo (rule 5 below) gives us close-ups automatically.

| Design | Missing |
|---|---|
| Indo-Arabic Back Hand | both close-ups |
| Bracelet & Finger Caps | close-up of the bracelet |
| Minimal Finger Trails | close-up of the finger medallions |

## How to take a catalog photo

1. **Fill the frame.** The hand or foot takes up most of the photo. No
   saree, rug or props stealing attention.
2. **Plain background.** A plain cloth, wall or table in one light colour.
3. **Daylight.** Near a window, no flash, no harsh shadows. Colours must
   look true - don't add filters.
4. **Finished stain.** Photograph the design after the paste is removed
   (the next day is best). Wet paste is acceptable only for designs that
   can't wait.
5. **Sharp and large.** Hold the phone steady and tap to focus on the
   design. At least 2000 pixels on the long side - the phone camera's
   normal setting is fine. No screenshots or WhatsApp-compressed copies.
6. **Show the whole design.** Palm designs: palm up, fingers spread.
   Back-hand designs: back of the hand up. Feet: from the side or above,
   toes to ankle.
7. **Extra views are welcome.** For each design: one main photo, then
   close-ups of the detail and the other side if it has one.
8. **Privacy.** No faces. For kids, only the hand. No real names or
   phone numbers in the design - use made-up initials.
9. **Natural henna only.** Brown-orange henna; no black henna, no alta
   or nail polish passed off as henna.

## How the photos get into the app

- **Artists:** upload under Profile → Designs I Offer, and tick "AryaVeda
  may use photos I upload as the main catalog photo". After the photo is
  approved, an admin can press "Use as catalog photo".
- **Admin:** Admin → Designs → "Needs a photo": upload the main photo,
  then press Show.
- **Developers (catalog files):** put the photo at
  `catalog/images/<slug>.jpg`, remove `photo_needed` from the design in
  `designs.json` and add its `photo` source, then run
  `catalog/name_images.py`, `catalog/build_gallery.py` and
  `seed_designs.py`.

## Making the catalog look like one shoot

`image-studio/` (repo root) checks each photo and gives every catalog
photo the same ivory backdrop, framing and colour look. The presets live
in `catalog/image-studio/`:

- `aryaveda-studio` - main photos and extra views: design cut out onto the
  site's ivory backdrop, square 1600px, colour matched to our reference
  photos.
- `aryaveda-detail` - close-ups: same colour look, square, real background
  kept.

The originals in `images/`, `angles/` and `gallery/` stay untouched;
`catalog/build_studio.py` writes the unified versions to `studio/`, and
`seed_designs.py` uploads those. After adding or changing any photo:

```bash
cd backend
venv/bin/python catalog/name_images.py
venv/bin/python catalog/build_gallery.py
../image-studio/.venv/bin/python catalog/build_studio.py    # ~15 s per new photo
venv/bin/python seed_designs.py
```

To preview a batch first:

```bash
cd image-studio
export IMAGE_STUDIO_PRESETS_DIR=../backend/catalog/image-studio
.venv/bin/image-studio process ../backend/catalog/images -o out --preset aryaveda-studio --sheet
```

`build_studio.py` lists photos that may be `blurry` or `low_resolution`.
Check those by eye - the blur check can miss mild blur - and replace any
that really are; editing cannot fix them.
