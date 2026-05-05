import math

class SCalc:
    @staticmethod
    def linear_interpolation(x, x0 ,x1, y1,y0):
        return y0 + (x - x0) * (y1 - y0) / (x1 - x0)

    @staticmethod
    def square_root_of_the_sum_of_squares(fb, ob):
        return math.hypot(fb, ob)
    


