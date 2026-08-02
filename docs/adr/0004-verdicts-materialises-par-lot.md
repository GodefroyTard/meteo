# Verdicts matérialisés par lot, API en lecture seule

L'Ex aequo repose sur un rééchantillonnage par blocs journaliers, trop coûteux pour être recalculé
à chaque requête HTTP sur plusieurs millions de Prévisions.

Un traitement par lot recalcule toutes les cases de Verdict et les écrit dans une table dédiée ;
l'API ne fait que les lire. Le système a donc deux rythmes distincts : un pipeline lourd et
périodique, une API qui répond instantanément.

## Conséquences

Les Verdicts affichés ont un âge, qu'il faut exposer. En contrepartie ils sont reproductibles et
inspectables — on peut rejouer un lot et comparer, ce qu'un calcul à la volée ne permet pas. Le
volume rend ce choix confortable : ~4 millions de Prévisions et ~176 000 Observations pour
8 Stations sur deux ans et demi, ce qu'un Postgres nu absorbe sans réglage particulier. Ni base
temporelle spécialisée ni moteur analytique séparé ne se justifient à cette échelle.
