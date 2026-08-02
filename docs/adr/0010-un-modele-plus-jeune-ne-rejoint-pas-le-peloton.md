# Un Modèle plus jeune que la période ne rejoint pas le peloton

Les modèles de prévision par apprentissage sont sortis des laboratoires : ECMWF exploite
**AIFS** en opérationnel, et Open-Meteo le sert, runs passés compris. La question « une
IA prévoit-elle mieux qu'un modèle physique, ici, dans cette vallée » devient donc
mesurable — c'est exactement celle que ce produit existe pour trancher.

Mais l'archive de ses runs passés ne commence que le **1er mars 2025**, mesurée le
02/08/2026 sur Grenoble, là où la période observée démarre le 04/02/2024.

## Pourquoi on ne peut pas simplement l'ajouter

L'alignement ne retient que les instants où **tous** les Modèles ont une valeur
(ADR 0005) : comparer des Modèles sur des instants différents reviendrait à comparer
des difficultés différentes, et un Modèle chanceux dans son échantillon paraîtrait
meilleur qu'un Modèle malchanceux dans le sien.

Verser AIFS dans le peloton principal appliquerait donc sa date de naissance à tout le
monde :

```
période observée   04/02/2024 → 02/08/2026     910 jours
communs avec AIFS                              519 jours   soit 57 %
seuil de publication                                        60 %
```

**Tous les Verdicts disparaîtraient**, à trois points du seuil — un an et demi
d'historique effacé pour accueillir un arrivant.

## Ce qu'on fait à la place

Deux classements cohabitent, et le périmètre entre dans la clé du Verdict :

- **complet** — toute la période observée, avec les seuls Modèles archivés depuis le
  début. C'est celui qui fait foi, c'est lui qui désigne le Modèle conseillé sur la
  page d'accueil, et il est inchangé ;
- **récent** — la fenêtre où les nouveaux venus existent aussi, avec tout le monde.

Le second est publié **à côté** du premier, précédé d'un avertissement qui dit ce qu'il
faut savoir pour le lire : la période n'est pas la même, le peloton non plus, et un
écart moyen n'y vaut que face aux autres écarts du même tableau.

Un nouveau venu porte `debut_archive` dans le catalogue. C'est cette date, et non une
liste tenue à la main, qui décide de son périmètre — le jour où l'archive d'AIFS
remontera plus loin, il suffira d'effacer la date pour qu'il rejoigne le peloton.

## Sa pastille est creuse, pas d'une septième couleur

La palette de l'ADR 0006 compte six teintes pour six Modèles. Lui en ajouter une
septième poserait deux problèmes.

Le premier est mesurable : la palette existante ne franchit déjà pas la validation
toutes paires confondues — `#008300` et `#eb6834` ne se séparent que de ΔE 3,2 en vision
protanope. Y ajouter une teinte aggraverait un défaut sans le traiter.

Le second est de fond : une septième couleur au même titre que les six ferait passer
AIFS pour un pair, alors que ses chiffres ne se comparent pas aux leurs. La distinction
passe donc par la **forme** — pastille creuse — comme le Prolongement de la page climat
se distingue par le tireté. C'est la règle constante du site : ce qui n'est pas de même
nature ne se distingue pas seulement par la couleur.

## Conséquences

Le second classement disparaîtra de lui-même quand `debut_archive` sera effacé, sans
qu'aucun code d'affichage n'ait à changer : le gabarit ne l'affiche que si des Modèles
récents existent.

Un contributeur pressé voudra fusionner les deux tableaux, ou déplacer la date de début
de la période observée pour « faire coïncider » tout le monde. Les deux effacent de
l'information : le premier en truquant la comparaison, le second en jetant un an et demi
d'observations.

Enfin, la collecte ne demande plus rien avant `debut_archive`. Sans cela, chaque passage
du lot ferait traverser à l'API dix-huit mois qu'elle ne peut pas servir.
