# Palette de séries validée, et son ordre

Le graphe de vérification superpose jusqu'à sept courbes : six Modèles et l'Observation.
Distinguer sept lignes fines qui se croisent est le cas le plus exigeant pour une palette,
et le choix des teintes ne peut pas se faire à l'œil.

Nous adoptons une palette catégorielle vérifiée par outil, dans les deux modes, contre les
surfaces réelles de la page. L'**ordre** des teintes fait partie de la décision, pas
seulement leur liste : c'est lui qui garantit que deux séries voisines restent séparables,
y compris en vision des couleurs déficiente.

| Rôle | Clair | Sombre |
|---|---|---|
| Observation | encre primaire | encre primaire |
| 1 — AROME | `#2a78d6` | `#3987e5` |
| 2 — ICON-D2 | `#eb6834` | `#d95926` |
| 3 — ARPEGE | `#1baf7a` | `#199e70` |
| 4 — ICON-EU | `#eda100` | `#c98500` |
| 5 — ECMWF | `#e87ba4` | `#d55181` |
| 6 — GFS | `#008300` | `#008300` |

L'Observation ne prend jamais une teinte de série : elle est tracée en encre primaire, plus
épaisse, et par-dessus les autres. Ce n'est pas une catégorie parmi d'autres, c'est la
référence contre laquelle tout est jugé.

Une teinte est attachée à un Modèle, jamais à son rang : masquer une série depuis la légende
ne repeint pas les autres. C'est pourquoi les Prévisions transitent en liste ordonnée et non
en objet JSON — le filtre `tojson` de Jinja2 trie les clés, ce qui dissocierait les couleurs
du graphe de celles du tableau.

## Conséquences

Trois teintes claires — vert d'eau, jaune, magenta — passent sous 3:1 de contraste sur fond
blanc. La contrepartie est obligatoire et fait partie de la décision : le graphe expose
une **vue tableau** de toutes les valeurs, et la légende porte les noms en toutes lettres.
Retirer le tableau invaliderait la palette.

Toute modification des teintes doit être revalidée dans les deux modes avant d'être retenue.
Les modifier « pour faire plus joli » sans repasser la validation casse une garantie
d'accessibilité qui ne se voit pas à l'écran d'un lecteur à vision normale.
