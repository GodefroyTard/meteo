# La Série longue raconte le lieu, elle ne juge aucun Modèle

La page climat introduit une source qui n'existait pas jusqu'ici : les séries climatologiques
quotidiennes de Météo-France, publiées par département sur data.gouv.fr sous licence ouverte
LOV2 et remontant à 1950 — parfois bien avant.

Cette source est **étanche** au reste du produit. Un Poste climatologique n'est pas une Station,
une Journée n'est pas une Observation, et rien de ce qui vient de Météo-France n'entre jamais dans
le calcul d'un Verdict.

## Pourquoi cette étanchéité

Trois raisons, dans l'ordre où elles mordent.

**Le pas de temps.** Une Prévision Open-Meteo est instantanée à l'heure pile ; une Observation
StatIC l'est aussi, c'est ce qui les rend comparables (ADR 0003). Un maximum quotidien n'est pas
la valeur d'un instant, c'est l'extremum d'une journée : le confronter à une Prévision horaire
comparerait deux grandeurs différentes.

**Le lieu.** Les Postes ne sont pas là où sont les Stations. Autrans est à 5 km d'Engins mais
164 m plus haut ; Grenoble-LVD est au même endroit que Saint-Martin-d'Hères mais ne mesure que
depuis 1999. Traiter l'un pour l'autre reviendrait exactement à ce que l'ADR 0003 interdit.

**Le service rendu.** Un Verdict répond à « à qui me fier pour demain ». Une Série longue répond
à « à quoi ressemblait ce jour ici ». La seconde question ne demande aucune Prévision, et sa
réponse ne s'améliore pas d'en avoir une.

## Ce que la Série longue autorise en revanche

**Un rattachement plus large.** Le coût de rattachement passe de 25 à 60 km équivalents pour un
Poste. Ce n'est pas un relâchement mais un changement de grandeur mesurée : une Observation sert à
juger une Prévision, il lui faut valoir pour le lieu au degré près ; une Série longue sert à montrer
une évolution, et le réchauffement est cohérent à l'échelle d'une région là où la température
absolue ne l'est pas. Le fond de vallée et l'alpage ne sont pas au même niveau, ils montent
ensemble. La contrepartie est obligatoire : le Poste est toujours nommé avec son altitude et son
écart au lieu.

**Un calcul à la volée.** L'ADR 0004 matérialise les Verdicts par lot parce qu'ils coûtent des
millions de lignes. Une Tendance s'ajuste sur soixante-dix points : la matérialiser demanderait
366 jours × 25 Postes × 2 séries de lignes précalculées pour économiser quelques microsecondes.
La règle de l'ADR 0004 vise le coût, pas la pureté ; elle ne s'applique donc pas ici.

## Les garde-fous, dans l'esprit de l'ADR 0005

Trois refus, échelonnés :

- une **année** ne compte que si la fenêtre de quinze jours porte au moins huit jours mesurés ;
- une **Tendance** n'est ajustée qu'à partir de trente années — la durée d'une normale au sens de
  l'OMM, seuil sous lequel la variabilité naturelle domine le signal ;
- une **pente** n'est déclarée significative que si son intervalle de confiance à 95 % exclut zéro.

Un Poste qui échoue au deuxième garde-fou affiche son nuage de points sans droite. Une pente qui
échoue au troisième s'affiche accompagnée de « donc indistinguable de zéro ». Dans les deux cas le
lecteur voit la donnée ; ce qu'on lui refuse, c'est la conclusion.

## Le Prolongement

Prolonger la droite jusqu'en 2050 est le point sur lequel il serait le plus facile de mentir. Trois
précautions le tiennent honnête :

- il est tracé en **tireté**, forme et non couleur, donc lisible sans percevoir les teintes ;
- une **frontière verticale** marque la dernière année mesurée ;
- la **bande d'incertitude s'évase** en s'éloignant du barycentre des années ajustées, comme le
  veut la formule ; à Autrans en 2050, elle vaut plusieurs degrés.

La page dit explicitement que ce n'est pas une prévision et qu'un vrai scénario climatique
demanderait des modèles de circulation et une trajectoire d'émissions. Les projections CMIP6 sont
accessibles par l'API climat d'Open-Meteo si l'on veut un jour les ajouter — ce serait alors une
section distincte, présentée comme un éventail de modèles et non comme une trajectoire.

## Le Cycle annuel, et pourquoi sa couleur n'est pas thermique

Le second graphe superpose toutes les années sur l'axe des quantièmes. Trois décisions
le rendent lisible sans le rendre trompeur.

**Le lissage sur trente et un jours** retire le temps qu'il fait et laisse la saison.
Il déplace les extrêmes, et la page le dit : une canicule de trois jours n'apparaît pas
sur ce graphe, elle se lit sur le premier en choisissant sa date. Sans lissage, cent
courbes de hérisson se confondraient en un bloc.

**Les décennies sont peintes d'une rampe séquentielle**, pas d'une palette catégorielle.
Ce qu'elles encodent est du temps, une grandeur ordonnée : une rampe d'une seule teinte,
du pâle au dense, se lit là où onze couleurs arbitraires demanderaient un aller-retour
constant vers la légende. La rampe est vérifiée en mode ordinal — luminosité monotone,
paliers visibles, extrémité pâle à plus de 2,8:1 sur les deux fonds.

**Sa teinte est celle de l'accent de l'interface, délibérément non thermique.** Le
premier graphe emploie déjà le chaud pour les maximales et le froid pour les minimales
(ADR 0007). Reprendre une rampe chaude pour « année récente » ferait croire que la
couleur dit la température, alors que c'est la hauteur de la courbe qui la dit — et le
message du graphe deviendrait une tautologie colorée. L'année en cours se distingue en
outre par l'épaisseur du trait et par son millésime en bout de courbe, de sorte qu'elle
reste repérable sans percevoir la nuance.

Les années non décennales sont tracées malgré tout, presque effacées. Elles ne sont pas
décoratives : c'est leur épaisseur collective qui donne l'échelle de ce qu'une année peut
faire, et sans elle les décennies sembleraient se succéder régulièrement.

## Les indicateurs comptés, et le piège des records

Trois graphes de plus reposent sur des **comptages** plutôt que sur des moyennes : les
Franchissements de seuil, la Saison sans gel, et les Records. Un comptage bouge beaucoup
là où une moyenne annuelle bouge peu, il se vérifie à la main, et il correspond à ce qu'on
vit. À Monestier, la moyenne de juillet gagne 2,3 °C en un siècle quand le nombre de jours
de gel passe de 127 à 66 par an.

Deux précautions valent pour les deux premiers :

- une année trop lacunaire est **écartée et non ramenée au prorata**. Extrapoler
  inventerait des gels qu'on n'a pas vus ; l'afficher tel quel dessinerait une fausse
  accalmie exactement là où la série se dégrade ;
- la droite ajustée **s'arrête à la dernière année mesurée**. Prolonger un comptage
  finirait par annoncer un nombre de jours de gel négatif — le Prolongement du premier
  graphe n'a de sens que parce qu'une température, elle, n'a pas de plancher.

**Les records demandent une précaution d'une autre nature**, et c'est le point sur lequel
ce graphe pourrait le plus facilement mentir. Publier le décompte brut par décennie ferait
passer pour un signal ce qui n'est qu'un effet du calendrier : une décennie complète
apporte dix années, une décennie tronquée trois, et la première paraîtrait mécaniquement
plus riche en records.

L'attente se calcule donc **jour par jour** : pour un jour du calendrier mesuré n fois,
chaque année en lice a une chance sur n de détenir le record, et la part attendue d'une
décennie est la somme de ces chances. Une année qui ne couvre que l'été ne pèse ainsi que
sur les jours d'été. Le graphe affiche le rapport de l'observé à cette attente, valant 1
sous un climat stable, accompagné de la bande que le hasard seul produit à deux
écarts-types.

Cette bande suppose les jours du calendrier indépendants. Ils ne le sont pas tout à fait —
deux jours voisins se ressemblent — de sorte que la vraie bande est un peu plus large que
celle affichée. La page le dit. À Monestier, les années 2020 détiennent 2,38 fois leur
part de records de chaleur et n'en ont battu aucun de froid, dans une bande de ±0,41 :
l'approximation ne change rien à la conclusion.

## Conséquences

Un contributeur verra deux jeux de températures en base et voudra les réconcilier : compléter les
Observations manquantes avec des Journées, ou juger les Modèles sur soixante-dix ans plutôt que sur
deux. C'est précisément ce qu'il ne faut pas faire. Les tables sont volontairement séparées et ne
partagent aucune clé.

Le chargement est départemental parce que les fichiers le sont. `METEO_DEPARTEMENTS_CLIMAT` fixe la
liste ; l'Isère seule pèse 988 000 journées pour 132 Postes, dont 25 franchissent le seuil des
trente années pleines.
