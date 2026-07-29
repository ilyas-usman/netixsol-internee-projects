Concept Check

What is the difference between .drop() and .dropna()?
>drop() we know what we are going to drop as we can drop by choosing specific entry while in >dropna() it drops every null(nan) value from the dataset.

How do you change the dtype of a column — and when would you need to?
when datatype of specific entry is not suitable like for calculating mean you cannot find mean of str so you have to convert it into int64 by using df["Age"] = df["Age"].astype(int)

What does .apply() do and how is it different from vectorized operations?
.apply() is applied on each entry of dataset and we use it when we want to apply specific or custom functionality and vectorized also applies on every entry but using built in functions like sum,min,max,*,+ etc.

Difference between .pivot() and .pivot_table()?
.pivot() just reshapes or rearranges the data and it gives value error on duplictes while >pivot_table() has a aggfunc() which handles duplicates and rearranes duplicates values in table and also rearranges whole table as well and accepts duplicates

What does .merge() do and what are the 4 types of joins?
>merge() merges or joins two dataframes on the basis of some common column may be id,department whatever is common in both tables
inner join-->it joins only common values and ignore others(intersection)
outer join-->it joins all values either common or not(union)
left join-->it joins all values from left table and coomon from right table
right join-->it joins all values from rght table and coomon from left table
