# La sécheresse se mesure par un bilan, pas par la pluie

L'intuition veut qu'une sécheresse soit un manque de pluie. Sur les Séries longues de
l'Isère, cette intuition est fausse, et il faut le dire avant de dessiner quoi que ce
soit.

À Monestier, sur soixante-quinze années mesurées, **aucun indicateur fondé sur la pluie
seule ne montre de tendance significative** : ni le cumul annuel (−0,4 mm/décennie
± 16,6), ni le cumul d'été (−3,5 ± 7,1), ni le nombre de jours secs (−0,6 ± 1,5), ni la
plus longue série sèche (−0,1 ± 0,7). Publier l'un de ces quatre graphes reviendrait à
dessiner du bruit et à laisser le lecteur y voir ce qu'il redoute.

Ce qui bouge, c'est la **demande**. À Grenoble-Saint-Geoirs, de mai à septembre et sur
cinquante-quatre saisons : l'évapotranspiration gagne 123 mm, la pluie en perd 95, et le
bilan se creuse de 215 mm. Les trois sont significatifs. La page mesure donc un bilan.

## Ne jamais estimer la demande depuis la température

La formule de Thornthwaite déduit l'évapotranspiration de la seule température moyenne.
Elle est tentante : elle aurait couvert les vingt-cinq Postes utilisables et serait
remontée à 1916, là où l'évapotranspiration publiée n'existe que sur vingt et un Postes
depuis 1968.

Confrontée à l'évapotranspiration Penman-Monteith que Météo-France publie à
Saint-Geoirs, sur cinquante-six années communes, elle donne 670 mm/an contre 890 — **soit
25 % de moins** — et une tendance de +13,2 contre +31,4 mm/décennie, **un facteur 2,4**.

Elle sous-estime donc l'assèchement de plus de moitié. Un Poste sans évapotranspiration
publiée n'a pas de section sécheresse : c'est un refus de conclure de plus, dans l'esprit
de l'ADR 0005, et il vaut mieux que la moitié d'une réponse.

## Deux évapotranspirations qui ne valent pas la même chose

`ETPMON` est calculée par Penman-Monteith depuis les mesures du Poste — vent, humidité,
rayonnement. Un seul Poste isérois en dispose sur assez d'années.

`ETPGRILLE` est interpolée sur une grille par Météo-France. Vingt Postes en ont. C'est un
produit d'analyse et non une mesure locale, ce qui est **en tension avec l'esprit de
l'ADR 0003** : nous refusons qu'une réanalyse tienne lieu d'Observation. Le refus tient
parce qu'aucun Modèle n'est jugé ici — mais l'écart n'est pas anecdotique. Au même Poste,
la grille donne un creusement de 139 mm là où Monteith en donne 215 : elle atténue le
signal d'environ un tiers.

Les deux sont donc stockées séparément, le Poste dit laquelle il retient, et la page le
nomme en toutes lettres. Une section fondée sur la grille se lit comme une borne basse.

## La saison, et non l'année

De mai à septembre. Hors saison, un déficit ne veut rien dire : il pleut moins en
janvier, mais rien ne pousse et rien n'évapore. C'est aussi la saison où le manque se
paie.

La couverture exigée y est bien plus stricte qu'ailleurs — 95 % des jours contre 90 %
pour un comptage annuel. Un cumul est une somme : cinq jours de pluie manquants sur cent
cinquante-trois retirent directement leurs millimètres du total, sans que rien ne le
signale.

## Une échelle standardisée par les rangs

L'indice place chaque saison parmi les autres du Poste : position de tracé de Gringorten,
puis quantile de la loi normale. C'est la méthode non paramétrique usuelle, et elle évite
d'imposer une famille de lois à une distribution de bilans hydriques qui n'est ni normale
ni gamma. Les seuils sont ceux de la littérature — −1, −1,5, −2 — pour que la page parle
la même langue que ce qu'un lecteur trouvera ailleurs.

Sa limite doit être affichée : **un indice construit par les rangs ne peut pas sortir de
l'échantillon.** Sur n saisons, la plus sèche vaut au mieux Φ⁻¹(0,44/(n+0,12)), soit
environ −2,3 pour cinquante ans. Une sécheresse inédite apparaîtra comme la plus sèche
connue, pas au-delà. La page le dit.

## Conséquences

La section n'existe que sur les Postes disposant d'évapotranspiration — vingt et un sur
deux cent sept en Isère. C'est peu, et c'est assumé.

Un contributeur voudra combler ce vide en estimant la demande depuis la température, ou
en substituant la grille à la mesure sans le dire. C'est précisément ce qu'il ne faut pas
faire : la première sous-estime le phénomène d'un facteur deux et demi, la seconde d'un
tiers.

C'est enfin une sécheresse **météorologique** : ni sol, ni nappe, ni fonte des neiges.
Elle dit ce que le ciel donne et reprend, pas ce que la terre en garde. Pour un massif
comme le Vercors, la fonte nivale compte beaucoup, et le même fichier départemental
publie la hauteur de neige sur quarante-six Postes — de quoi ouvrir un jour ce chapitre.
