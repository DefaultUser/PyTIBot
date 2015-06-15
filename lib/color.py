
## \brief Maps color names to the corresponding mIRC numerical values
## (as a two-digit strings)
color_code = {
    "black"       : "00",
    "white"       : "01",
    "dark_blue"   : "02",
    "dark_green"  : "03",
    "red"         : "04",
    "dark_red"    : "05",
    "dark_magenta": "06",
    "dark_yellow" : "07",
    "yellow"      : "08",
    "green"       : "09",
    "dark_cyan"   : "10",
    "cyan"        : "11",
    "blue"        : "12",
    "magenta"     : "13",
    "dark_gray"   : "14",
    "gray"        : "15"
}

## \brief Return a color in the rainbow
## \param factor        A value in [0,1]
## \param colors        Color names to be featured in the rainbow
## \returns The numerical value of the selected color
def rainbow_color(factor, colors):
    return color_code[colors[int(factor*len(colors))]]

## \brief Colorize a string as a rainbow
## \param text          Input text
## \param colors        Color names to be featured in the rainbow
## \returns A string with valid IRC color codes inserted at the right positions
def rainbow(text, colors=["red","dark_yellow","green","cyan","blue","magenta"]) :
    ret = ""
    color = ""
    for index, char in enumerate(text):
        newcolor = rainbow_color(float(index)/len(text), colors)
        if newcolor != color:
            color = newcolor
            ret += "\03"+color
        ret += char
    return ret
