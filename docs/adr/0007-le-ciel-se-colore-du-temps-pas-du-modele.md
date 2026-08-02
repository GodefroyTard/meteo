# Le ciel se colore du Temps, pas du Modèle

La page d'accueil s'ouvre sur une bande de ciel dont la couleur suit le Temps annoncé :
azur quand c'est dégagé, ardoise sous la pluie, violine sous l'orage, indigo la nuit. Cette
bande donne le ton ; le reste de la page tient au gris d'instrument, sauf le panneau de
conditions où la couleur dit l'état d'une mesure.

Trois jeux de couleurs coexistent donc, et ils ne doivent jamais se croiser.

| Ce qui est coloré | D'après quoi | Où |
|---|---|---|
| La bande de ciel, la teinte d'une heure pluvieuse | le **Temps** — famille du code WMO | `--ciel-*` dans `page.css` |
| Le filet d'une carte, la pastille du rail et du tableau | le **Modèle** — rang dans le catalogue | `--serie-*`, fixé par [ADR 0006](0006-palette-de-series-validee.md) |
| Le lavé, la puce et la jauge d'une cellule de conditions | l'**état mesuré** — niveau d'UV, force du vent, qualité de l'air, chaud ou froid | `--risque-*`, `--ton-*`, `--souffle`, `--eau`, `--astre`, `--glace`, `--ardoise` |

## Le troisième jeu, et ce qui l'autorise

Les deux premiers jeux disent *qui parle*. Le troisième dit *où en est une mesure* :
un indice UV de 9 est rouge parce qu'il est dangereux, pas parce qu'il appartient à
quelqu'un. Neuf cellules à l'encre grise ne se lisaient pas — la couleur y fait un vrai
travail, celui de rendre un état saisissable avant lecture.

Trois règles le rendent compatible avec les deux autres :

- **La forme sépare les jeux.** Les teintes d'état n'apparaissent qu'en fond lavé, en
  puce d'icône et en jauge. Elles ne prennent jamais la forme d'une pastille ronde ni
  d'un filet vertical — ces deux formes-là appartiennent aux Modèles, partout sur le site.
- **Un seul barème de gravité.** L'échelle `--risque-1..6` sert l'indice UV, la qualité
  de l'air et le vent au-delà de « soutenu ». On n'invente pas une échelle par mesure :
  moins il y a de couleurs, plus chacune veut dire quelque chose.
- **La couleur ne porte jamais seule.** Chaque cellule écrit son état en toutes lettres —
  « modéré », « protection conseillée », « plus chaud que d'habitude ». Le chiffre reste
  à l'encre ; retirer la couleur ne retirerait aucune information.

## Pourquoi les séparer

Un Modèle garde sa teinte quel que soit le temps qu'il annonce : c'est ce qui permet de
suivre AROME du rail au graphe en passant par le tableau. Si le bleu servait aussi à dire
« ciel dégagé », la lecture deviendrait ambiguë au premier coup d'œil — et c'est précisément
le coup d'œil que la bande de ciel sert.

Inversement, colorer le ciel d'après le Modèle conseillé ferait changer la page de couleur
quand on change de saison ou d'anticipation, alors que le temps qu'il fait, lui, n'a pas
bougé.

## Conséquences

- Les six teintes de série ne colorent jamais de texte. Trois d'entre elles ne passent pas
  3:1 sur fond blanc (ADR 0006) : dans la phrase du Verdict, le nom du Modèle reste à
  l'encre et c'est une pastille qui porte l'identité.
- Le texte posé sur la bande de ciel est blanc. Un voile sombre dégradé garantit un plancher
  de contraste sur toute la largeur du haut de bande, y compris sous les ciels pâles —
  brouillard et couvert. Ajouter une famille de ciel oblige à revérifier ce plancher.
- Un Modèle qui n'annonce pas de Temps n'en reçoit pas un d'office. AROME ne publie aucun
  code WMO : sa carte porte l'icône « temps non annoncé », et la bande de ciel emprunte le
  Temps d'un autre Modèle en le nommant. Déduire « ciel dégagé » de l'absence de pluie
  serait une affirmation que personne n'a faite.
