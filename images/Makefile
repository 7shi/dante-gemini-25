# See README.md for the overall pipeline this drives.
#
# The images themselves (dante.jpg, dante-*.jpg, {part}-title/-last.jpg,
# {part}/NN.jpg) and their prompts ({part}/NN.txt) are not tracked in git;
# they are put in place out-of-band. Everything below is a no-op once the
# files it targets already exist, so a plain `make` never calls the
# image-generation API by accident.

.PHONY: all reference illustrations titles

all: reference illustrations titles

reference: dante.jpg dante-virgil.jpg dante-beatrice.jpg dante-3.jpg

dante.jpg:
	uv run generate-reference.py -o dante.jpg --prompt-file characters.txt

dante-virgil.jpg: dante.jpg
	uv run generate-reference.py dante.jpg -o dante-virgil.jpg --characters Dante,Virgil

dante-beatrice.jpg: dante.jpg
	uv run generate-reference.py dante.jpg -o dante-beatrice.jpg --characters Dante,Beatrice

dante-3.jpg: dante.jpg
	uv run generate-reference.py dante.jpg -o dante-3.jpg --characters Dante,Virgil,Beatrice

illustrations: dante-virgil.jpg dante-beatrice.jpg
	uv run generate-image.py dante-virgil.jpg -p inferno purgatorio
	uv run generate-image.py dante-beatrice.jpg -p paradiso --characters Dante,Beatrice

titles: dante-virgil.jpg dante-beatrice.jpg
	uv run generate-image.py dante-virgil.jpg -p inferno --title inferno-title.txt
	uv run generate-image.py dante-virgil.jpg -p purgatorio --title purgatorio-title.txt
	uv run generate-image.py dante-beatrice.jpg -p paradiso --title paradiso-title.txt --characters Dante,Beatrice
	uv run generate-image.py dante-virgil.jpg -p inferno --title inferno-last.txt
	uv run generate-image.py dante-virgil.jpg -p purgatorio --title purgatorio-last.txt
	uv run generate-image.py dante-beatrice.jpg -p paradiso --title paradiso-last.txt --characters Dante,Beatrice
